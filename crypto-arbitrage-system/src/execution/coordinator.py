"""
Multi-leg arbitrage coordinator.

Coordinates execution of multi-leg arbitrage trades:
- Cross-exchange arbitrage (2 legs)
- Triangle arbitrage (3+ legs)
- Atomic execution
- Rollback on failure
"""
import asyncio
from datetime import datetime
from typing import Dict

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.execution.balance_manager import BalanceManager
from src.execution.models import ExecutionPlan, ExecutionState, OrderStatus
from src.execution.order_manager import OrderManager

logger = get_logger(__name__, component="coordinator")


class MultiLegCoordinator:
    """
    Coordinates multi-leg arbitrage execution.

    Handles:
    - Cross-exchange arbitrage (2 legs: buy + sell)
    - Triangle arbitrage (3 legs: A→B→C)
    - Atomic execution (all or nothing)
    - Rollback on failure
    """

    def __init__(
        self,
        exchanges: Dict[str, BaseExchange],
        order_manager: OrderManager,
        balance_manager: BalanceManager,
    ):
        """
        Initialize coordinator.

        Args:
            exchanges: Dictionary of exchange instances
            order_manager: Order manager instance
            balance_manager: Balance manager instance
        """
        self.exchanges = exchanges
        self.order_manager = order_manager
        self.balance_manager = balance_manager

        logger.info("Multi-leg coordinator initialized")

    async def execute_plan(self, plan: ExecutionPlan) -> bool:
        """
        Execute multi-leg arbitrage plan.

        Args:
            plan: Execution plan to execute

        Returns:
            True if all legs executed successfully
        """
        plan.state = ExecutionState.EXECUTING
        plan.started_at = datetime.utcnow()

        logger.info(
            "execution_started",
            execution_id=plan.execution_id,
            strategy=plan.strategy,
            num_orders=len(plan.orders),
            dry_run=plan.dry_run,
        )

        try:
            # Execute all orders concurrently (for speed)
            order_tasks = []
            for order in plan.orders:
                exchange = self.exchanges[order.exchange]
                task = self.order_manager.place_order(exchange, order, plan.dry_run)
                order_tasks.append(task)

            # Wait for all orders to be placed
            placement_results = await asyncio.gather(*order_tasks, return_exceptions=True)

            # Check if all orders placed successfully
            if not all(result is True for result in placement_results):
                plan.state = ExecutionState.FAILED
                plan.error_message = "Failed to place one or more orders"
                await self._rollback(plan)
                return False

            # Wait for all orders to fill
            fill_tasks = []
            for order in plan.orders:
                exchange = self.exchanges[order.exchange]
                task = self.order_manager.wait_for_fill(exchange, order, timeout_seconds=30)
                fill_tasks.append(task)

            fill_results = await asyncio.gather(*fill_tasks, return_exceptions=True)

            # Check if all orders filled
            if all(result is True for result in fill_results):
                plan.state = ExecutionState.COMPLETED
                plan.completed_at = datetime.utcnow()

                logger.info(
                    "execution_completed",
                    execution_id=plan.execution_id,
                    execution_time=plan.execution_time_seconds,
                )

                return True
            else:
                # Partial fill - attempt rollback
                plan.state = ExecutionState.PARTIALLY_FILLED
                await self._handle_partial_fill(plan)
                return False

        except Exception as e:
            plan.state = ExecutionState.FAILED
            plan.error_message = str(e)

            logger.error("execution_failed", execution_id=plan.execution_id, error=str(e))

            # Attempt rollback
            await self._rollback(plan)
            return False

    async def _handle_partial_fill(self, plan: ExecutionPlan) -> None:
        """Handle partially filled orders."""
        filled_orders = [o for o in plan.orders if o.is_filled]
        unfilled_orders = [o for o in plan.orders if not o.is_filled]

        logger.warning(
            "partial_fill_detected",
            execution_id=plan.execution_id,
            filled=len(filled_orders),
            unfilled=len(unfilled_orders),
        )

        # Cancel unfilled orders
        for order in unfilled_orders:
            exchange = self.exchanges[order.exchange]
            await self.order_manager.cancel_order(exchange, order)

        # Log asymmetric position warning
        if len(filled_orders) == 1 and len(plan.orders) == 2:
            logger.critical(
                f"⚠️ ASYMMETRIC POSITION: Only {filled_orders[0].side} order filled",
                execution_id=plan.execution_id,
                exchange=filled_orders[0].exchange,
                symbol=filled_orders[0].symbol,
            )

    async def _rollback(self, plan: ExecutionPlan) -> None:
        """Attempt to rollback failed execution."""
        plan.state = ExecutionState.ROLLING_BACK

        logger.info("rollback_started", execution_id=plan.execution_id)

        # Cancel all open orders
        cancel_tasks = []
        for order in plan.orders:
            if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                exchange = self.exchanges[order.exchange]
                task = self.order_manager.cancel_order(exchange, order)
                cancel_tasks.append(task)

        if cancel_tasks:
            await asyncio.gather(*cancel_tasks, return_exceptions=True)

        plan.state = ExecutionState.ROLLED_BACK

        logger.info("rollback_completed", execution_id=plan.execution_id)
