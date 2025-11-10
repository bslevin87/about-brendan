"""
Execution data models.

Defines core structures for order execution:
- Execution states and order statuses
- Order tracking
- Execution plans
- Execution results
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import uuid4


class ExecutionState(Enum):
    """Execution lifecycle states."""

    PENDING = "pending"  # Awaiting execution
    VALIDATING = "validating"  # Risk validation in progress
    APPROVED = "approved"  # Passed validation
    REJECTED = "rejected"  # Failed validation
    EXECUTING = "executing"  # Orders being placed
    PARTIALLY_FILLED = "partially_filled"  # Some orders filled
    COMPLETED = "completed"  # All orders filled successfully
    FAILED = "failed"  # Execution failed
    ROLLING_BACK = "rolling_back"  # Attempting to rollback
    ROLLED_BACK = "rolled_back"  # Successfully rolled back


class OrderStatus(Enum):
    """Order status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class ExecutionOrder:
    """
    Individual order within an execution.

    Tracks single order from creation through completion.
    """

    order_id: str = field(default_factory=lambda: str(uuid4()))
    exchange: str = ""
    symbol: str = ""
    side: str = ""  # "buy" or "sell"
    order_type: str = "limit"
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None

    # Execution details
    status: OrderStatus = OrderStatus.PENDING
    exchange_order_id: Optional[str] = None
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Optional[Decimal] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

    # Fees
    fee_amount: Decimal = Decimal("0")
    fee_currency: str = ""

    # Attempts and errors
    attempt_count: int = 0
    last_error: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def fill_percentage(self) -> Decimal:
        """Calculate fill percentage."""
        if self.quantity == 0:
            return Decimal("0")
        return (self.filled_quantity / self.quantity) * Decimal("100")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ExecutionOrder(id={self.order_id[:8]}, {self.exchange}, "
            f"{self.symbol}, {self.side}, {self.status.value})"
        )


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for an arbitrage opportunity.

    Tracks the full lifecycle from validation through completion.
    """

    execution_id: str = field(default_factory=lambda: str(uuid4()))
    opportunity_id: str = ""
    strategy: str = ""  # "cross_exchange", "triangle"

    # Orders (for cross-exchange: 2 orders, for triangle: 3+ orders)
    orders: List[ExecutionOrder] = field(default_factory=list)

    # State tracking
    state: ExecutionState = ExecutionState.PENDING

    # Expected results
    expected_profit_usd: Decimal = Decimal("0")
    expected_profit_percent: Decimal = Decimal("0")

    # Actual results
    actual_profit_usd: Optional[Decimal] = None
    actual_profit_percent: Optional[Decimal] = None
    total_fees_usd: Decimal = Decimal("0")

    # Execution metadata
    dry_run: bool = True  # Default to dry-run for safety
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error tracking
    error_message: Optional[str] = None
    rollback_reason: Optional[str] = None

    @property
    def execution_time_seconds(self) -> Optional[float]:
        """Calculate execution time."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_successful(self) -> bool:
        """Check if execution was successful."""
        return self.state == ExecutionState.COMPLETED

    @property
    def all_orders_filled(self) -> bool:
        """Check if all orders are filled."""
        return all(order.is_filled for order in self.orders)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ExecutionPlan(id={self.execution_id[:8]}, "
            f"{self.strategy}, {self.state.value}, "
            f"{len(self.orders)} orders)"
        )


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""

    execution_id: str
    success: bool
    state: ExecutionState
    profit_usd: Optional[Decimal] = None
    execution_time_seconds: Optional[float] = None
    orders_filled: int = 0
    total_orders: int = 0
    error_message: Optional[str] = None

    def __repr__(self) -> str:
        """String representation."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"ExecutionResult({status}, {self.orders_filled}/{self.total_orders} filled)"
        )
