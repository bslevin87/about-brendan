"""
Main execution engine.

Orchestrates arbitrage trade execution:
- Risk validation
- Order placement
- Multi-leg coordination
- Reconciliation
- P&L tracking
"""
from decimal import Decimal
from typing import Dict, Optional

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.execution.balance_manager import BalanceManager
from src.execution.coordinator import MultiLegCoordinator
from src.execution.models import (
    ExecutionOrder,
    ExecutionPlan,
    ExecutionResult,
    ExecutionState,
)
from src.execution.order_manager import OrderManager
from src.execution.reconciliation import ReconciliationEngine
from src.models.opportunity import ArbitrageOpportunity
from src.risk.manager import RiskManager

logger = get_logger(__name__, component="execution_engine")


class ExecutionEngine:
    """
    Main execution engine for arbitrage trading.

    Orchestrates:
    - Risk validation
    - Order placement
    - Multi-leg coordination
    - Reconciliation
    - P&L tracking
    """

    def __init__(
        self,
        exchanges: Dict[str, BaseExchange],
        risk_manager: RiskManager,
        config,
    ):
        """
        Initialize execution engine.

        Args:
            exchanges: Dictionary of exchange instances
            risk_manager: Risk manager instance
            config: ConfigManager instance
        """
        self.exchanges = exchanges
        self.risk_manager = risk_manager
        self.config = config

        # Initialize components
        self.order_manager = OrderManager()
        self.balance_manager = BalanceManager(exchanges)
        self.coordinator = MultiLegCoordinator(
            exchanges, self.order_manager, self.balance_manager
        )
        self.reconciliation = ReconciliationEngine()

        # Execution tracking
        self.executions: Dict[str, ExecutionPlan] = {}

        logger.info("Execution engine initialized")

    async def initialize(self) -> None:
        """Initialize engine (fetch balances, etc.)."""
        await self.balance_manager.refresh_balances()

        logger.info("Execution engine ready")

    async def execute_opportunity(
        self, opportunity: ArbitrageOpportunity, dry_run: bool = True
    ) -> ExecutionResult:
        """
        Execute an arbitrage opportunity.

        Main entry point for execution.

        Args:
            opportunity: Arbitrage opportunity to execute
            dry_run: If True, simulate without real execution

        Returns:
            ExecutionResult with outcome
        """
        # Create execution plan
        plan = self._create_execution_plan(opportunity, dry_run)

        logger.info(
            "executing_opportunity",
            execution_id=plan.execution_id,
            opportunity_id=opportunity.opportunity_id,
            strategy=opportunity.strategy,
            expected_profit=float(opportunity.net_profit_usd),
            dry_run=dry_run,
        )

        # Track execution
        self.executions[plan.execution_id] = plan

        # Step 1: Validate with risk manager
        plan.state = ExecutionState.VALIDATING

        validation = self.risk_manager.validate_trade(
            opportunity, self._get_available_balances()
        )

        if not validation.passed:
            plan.state = ExecutionState.REJECTED
            plan.error_message = validation.reason

            logger.warning(
                "execution_rejected",
                execution_id=plan.execution_id,
                reason=validation.reason,
            )

            return ExecutionResult(
                execution_id=plan.execution_id,
                success=False,
                state=plan.state,
                error_message=validation.reason,
            )

        plan.state = ExecutionState.APPROVED

        # Step 2: Reserve balances
        if not self._reserve_balances(plan):
            plan.state = ExecutionState.FAILED
            plan.error_message = "Failed to reserve balances"

            return ExecutionResult(
                execution_id=plan.execution_id,
                success=False,
                state=plan.state,
                error_message="Failed to reserve balances",
                total_orders=len(plan.orders),
            )

        # Step 3: Execute orders
        success = await self.coordinator.execute_plan(plan)

        # Step 4: Reconcile if successful
        if success:
            self.reconciliation.reconcile(plan)

            # Record with risk manager
            if not dry_run:
                # Open position tracking
                for order in plan.orders:
                    if order.is_filled and order.side == "buy":
                        self.risk_manager.open_position(
                            position_id=f"{plan.execution_id}_{order.order_id}",
                            exchange=order.exchange,
                            symbol=order.symbol,
                            side="long",
                            quantity=order.filled_quantity,
                            entry_price=order.average_fill_price or order.price,
                        )

                # Record trade outcome
                self.risk_manager.record_trade_outcome(
                    position_id=plan.execution_id,
                    pnl_usd=plan.actual_profit_usd or Decimal("0"),
                    trade_details={
                        "strategy": plan.strategy,
                        "execution_time": plan.execution_time_seconds,
                    },
                )

        # Step 5: Release balances
        self._release_balances(plan)

        # Create result
        return ExecutionResult(
            execution_id=plan.execution_id,
            success=success,
            state=plan.state,
            profit_usd=plan.actual_profit_usd if success else None,
            execution_time_seconds=plan.execution_time_seconds,
            orders_filled=sum(1 for o in plan.orders if o.is_filled),
            total_orders=len(plan.orders),
            error_message=plan.error_message,
        )

    def _create_execution_plan(
        self, opportunity: ArbitrageOpportunity, dry_run: bool
    ) -> ExecutionPlan:
        """Create execution plan from opportunity."""
        plan = ExecutionPlan(
            opportunity_id=opportunity.opportunity_id,
            strategy=opportunity.strategy,
            expected_profit_usd=opportunity.net_profit_usd,
            expected_profit_percent=opportunity.net_profit_percent,
            dry_run=dry_run,
        )

        # Create orders based on strategy
        if opportunity.strategy == "cross_exchange":
            # Buy order
            buy_order = ExecutionOrder(
                exchange=opportunity.buy_exchange,
                symbol=opportunity.symbol,
                side="buy",
                order_type="limit",
                quantity=opportunity.max_quantity,
                price=opportunity.buy_price,
            )
            plan.orders.append(buy_order)

            # Sell order
            sell_order = ExecutionOrder(
                exchange=opportunity.sell_exchange,
                symbol=opportunity.symbol,
                side="sell",
                order_type="limit",
                quantity=opportunity.max_quantity,
                price=opportunity.sell_price,
            )
            plan.orders.append(sell_order)

        # TODO: Add triangle arbitrage order creation

        return plan

    def _reserve_balances(self, plan: ExecutionPlan) -> bool:
        """Reserve balances for execution."""
        for order in plan.orders:
            if order.side == "buy":
                # Need quote currency (e.g., USD for BTC/USD)
                currency = "USD"  # Simplified
                amount = order.quantity * (order.price or Decimal("0"))

                if not self.balance_manager.reserve_balance(
                    order.exchange, currency, amount
                ):
                    return False

        return True

    def _release_balances(self, plan: ExecutionPlan) -> None:
        """Release reserved balances."""
        for order in plan.orders:
            if order.side == "buy":
                currency = "USD"
                amount = order.quantity * (order.price or Decimal("0"))
                self.balance_manager.release_balance(order.exchange, currency, amount)

    def _get_available_balances(self) -> dict:
        """Get available balances for risk validation."""
        return self.balance_manager.available_balances

    def get_execution_status(self, execution_id: str) -> Optional[ExecutionPlan]:
        """
        Get status of an execution.

        Args:
            execution_id: Execution ID to look up

        Returns:
            ExecutionPlan if found, None otherwise
        """
        return self.executions.get(execution_id)

    def get_stats(self) -> dict:
        """
        Get execution statistics.

        Returns:
            Dictionary with execution stats
        """
        total_executions = len(self.executions)
        successful = sum(1 for p in self.executions.values() if p.is_successful)
        failed = sum(
            1
            for p in self.executions.values()
            if p.state in [ExecutionState.FAILED, ExecutionState.ROLLED_BACK]
        )

        return {
            "total_executions": total_executions,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total_executions * 100) if total_executions > 0 else 0,
            "balance_stats": self.balance_manager.get_stats(),
        }
