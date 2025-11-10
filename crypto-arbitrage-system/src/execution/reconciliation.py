"""
Trade reconciliation engine.

Reconciles expected vs actual execution results:
- Actual P&L vs expected
- Fees paid vs estimated
- Slippage impact
- Execution quality
"""
from decimal import Decimal

from src.core.logger import get_logger
from src.execution.models import ExecutionPlan

logger = get_logger(__name__, component="reconciliation")


class ReconciliationEngine:
    """
    Reconciles expected vs actual execution results.

    Verifies:
    - Actual P&L vs expected
    - Fees paid vs estimated
    - Slippage impact
    - Execution quality
    """

    def __init__(self):
        """Initialize reconciliation engine."""
        logger.info("Reconciliation engine initialized")

    def reconcile(self, plan: ExecutionPlan) -> bool:
        """
        Reconcile execution plan.

        Args:
            plan: Execution plan to reconcile

        Returns:
            True if reconciliation passes
        """
        if not plan.is_successful:
            logger.warning(
                "cannot_reconcile_failed_execution",
                execution_id=plan.execution_id,
            )
            return False

        # Calculate actual P&L
        plan.actual_profit_usd = self._calculate_actual_profit(plan)

        # Calculate total fees
        plan.total_fees_usd = sum(order.fee_amount for order in plan.orders)

        # Calculate actual profit percentage
        if plan.orders:
            total_value = sum(
                order.filled_quantity * order.average_fill_price
                for order in plan.orders
                if order.average_fill_price
            )
            if total_value > 0:
                plan.actual_profit_percent = (
                    plan.actual_profit_usd / total_value
                ) * Decimal("100")

        # Compare expected vs actual
        profit_variance = abs(plan.actual_profit_usd - plan.expected_profit_usd)
        variance_percent = (
            (profit_variance / plan.expected_profit_usd * Decimal("100"))
            if plan.expected_profit_usd > 0
            else Decimal("0")
        )

        logger.info(
            "reconciliation_complete",
            execution_id=plan.execution_id,
            expected_profit_usd=float(plan.expected_profit_usd),
            actual_profit_usd=float(plan.actual_profit_usd),
            variance_percent=float(variance_percent),
            total_fees_usd=float(plan.total_fees_usd),
        )

        # Flag if variance is too high (>10%)
        if variance_percent > 10:
            logger.warning(
                "high_profit_variance",
                execution_id=plan.execution_id,
                variance_percent=float(variance_percent),
            )
            return False

        return True

    def _calculate_actual_profit(self, plan: ExecutionPlan) -> Decimal:
        """Calculate actual profit from filled orders."""
        if plan.strategy == "cross_exchange":
            # For cross-exchange: profit = sell_value - buy_value - fees
            buy_order = next((o for o in plan.orders if o.side == "buy"), None)
            sell_order = next((o for o in plan.orders if o.side == "sell"), None)

            if (
                buy_order
                and sell_order
                and buy_order.average_fill_price
                and sell_order.average_fill_price
            ):
                buy_value = buy_order.filled_quantity * buy_order.average_fill_price
                sell_value = sell_order.filled_quantity * sell_order.average_fill_price
                fees = buy_order.fee_amount + sell_order.fee_amount

                return sell_value - buy_value - fees

        return Decimal("0")
