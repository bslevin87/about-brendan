"""
Order management system.

Manages individual order placement and tracking:
- Order submission with retries
- Order status tracking
- Partial fill handling
- Order cancellation
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.execution.models import ExecutionOrder, OrderStatus

logger = get_logger(__name__, component="order_manager")


class OrderManager:
    """
    Manages individual order placement and tracking.

    Handles:
    - Order submission with retries
    - Order status tracking
    - Partial fill handling
    - Order cancellation
    """

    def __init__(self):
        """Initialize order manager."""
        # Active orders: {order_id: ExecutionOrder}
        self.active_orders: Dict[str, ExecutionOrder] = {}

        logger.info("Order manager initialized")

    async def place_order(
        self, exchange: BaseExchange, order: ExecutionOrder, dry_run: bool = True
    ) -> bool:
        """
        Place an order on an exchange.

        Args:
            exchange: Exchange instance
            order: Order to place
            dry_run: If True, simulate order without real execution

        Returns:
            True if order placed successfully
        """
        order.attempt_count += 1
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = datetime.utcnow()

        try:
            # Place order via exchange
            exchange_order = await self._place_with_retry(exchange, order, dry_run)

            # Update order with exchange details
            order.exchange_order_id = exchange_order.order_id
            order.status = OrderStatus.OPEN

            # Track active order
            self.active_orders[order.order_id] = order

            logger.info(
                "order_placed",
                order_id=order.order_id,
                exchange_order_id=order.exchange_order_id,
                exchange=order.exchange,
                symbol=order.symbol,
                side=order.side,
                quantity=float(order.quantity),
                price=float(order.price) if order.price else None,
                dry_run=dry_run,
            )

            return True

        except Exception as e:
            order.status = OrderStatus.FAILED
            order.last_error = str(e)

            logger.error(
                "order_placement_failed",
                order_id=order.order_id,
                exchange=order.exchange,
                error=str(e),
                attempt=order.attempt_count,
            )

            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
    async def _place_with_retry(
        self, exchange: BaseExchange, order: ExecutionOrder, dry_run: bool
    ):
        """Place order with automatic retry."""
        return await exchange.create_order(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            amount=order.quantity,
            price=order.price,
        )

    async def check_order_status(
        self, exchange: BaseExchange, order: ExecutionOrder
    ) -> bool:
        """
        Check order status on exchange.

        Args:
            exchange: Exchange instance
            order: Order to check

        Returns:
            True if order is filled
        """
        if not order.exchange_order_id:
            return False

        try:
            exchange_order = await exchange.fetch_order(
                order.exchange_order_id, order.symbol
            )

            # Update order details
            order.filled_quantity = exchange_order.filled
            order.status = self._map_status(exchange_order.status)

            if order.filled_quantity > 0 and exchange_order.price:
                order.average_fill_price = exchange_order.price

            if order.status == OrderStatus.FILLED:
                order.filled_at = datetime.utcnow()

                logger.info(
                    "order_filled",
                    order_id=order.order_id,
                    filled_quantity=float(order.filled_quantity),
                    average_price=(
                        float(order.average_fill_price)
                        if order.average_fill_price
                        else None
                    ),
                )

            return order.is_filled

        except Exception as e:
            logger.error("order_status_check_failed", order_id=order.order_id, error=str(e))
            return False

    async def cancel_order(
        self, exchange: BaseExchange, order: ExecutionOrder
    ) -> bool:
        """
        Cancel an open order.

        Args:
            exchange: Exchange instance
            order: Order to cancel

        Returns:
            True if cancelled successfully
        """
        if not order.exchange_order_id:
            return False

        try:
            success = await exchange.cancel_order(order.exchange_order_id, order.symbol)

            if success:
                order.status = OrderStatus.CANCELLED
                self.active_orders.pop(order.order_id, None)

                logger.info("order_cancelled", order_id=order.order_id)

            return success

        except Exception as e:
            logger.error("order_cancellation_failed", order_id=order.order_id, error=str(e))
            return False

    async def wait_for_fill(
        self,
        exchange: BaseExchange,
        order: ExecutionOrder,
        timeout_seconds: int = 30,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Wait for order to fill with timeout.

        Args:
            exchange: Exchange instance
            order: Order to wait for
            timeout_seconds: Maximum time to wait
            poll_interval: How often to check status

        Returns:
            True if filled within timeout
        """
        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).total_seconds() < timeout_seconds:
            if await self.check_order_status(exchange, order):
                return True

            await asyncio.sleep(poll_interval)

        # Timeout reached
        logger.warning(
            "order_fill_timeout",
            order_id=order.order_id,
            timeout_seconds=timeout_seconds,
            filled_quantity=float(order.filled_quantity),
            target_quantity=float(order.quantity),
        )

        return False

    def _map_status(self, exchange_status: str) -> OrderStatus:
        """Map exchange status to OrderStatus."""
        status_map = {
            "pending": OrderStatus.PENDING,
            "open": OrderStatus.OPEN,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return status_map.get(exchange_status, OrderStatus.OPEN)
