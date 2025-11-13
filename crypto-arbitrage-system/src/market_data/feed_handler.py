"""
WebSocket feed handler for real-time market data.

Manages WebSocket feeds from all exchanges, parsing and normalizing
incoming data, updating order books, and triggering callbacks.
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.market_data.cache import MarketDataCache
from src.market_data.order_book_manager import OrderBookManager

logger = get_logger(__name__, component="feed_handler")


class FeedHandler:
    """
    Manages WebSocket feeds from all exchanges.

    Responsibilities:
    - Subscribe to order book updates
    - Parse and normalize incoming data
    - Update order book manager
    - Cache data in Redis
    - Trigger callbacks on updates
    """

    def __init__(
        self,
        exchanges: Dict[str, BaseExchange],
        order_book_manager: OrderBookManager,
        cache: MarketDataCache,
    ) -> None:
        """
        Initialize feed handler.

        Args:
            exchanges: Dictionary mapping exchange names to exchange instances
            order_book_manager: Order book manager instance
            cache: Market data cache instance
        """
        self.exchanges = exchanges
        self.order_book_manager = order_book_manager
        self.cache = cache
        self.running = False
        self.tasks: List[asyncio.Task] = []

        # Callbacks to trigger on order book updates
        self.callbacks: List[Callable] = []

        # Statistics
        self.updates_received = 0
        self.updates_failed = 0

    def register_callback(self, callback: Callable) -> None:
        """
        Register callback to be called on every order book update.

        Args:
            callback: Async callable that takes (exchange, symbol, bids, asks)
        """
        self.callbacks.append(callback)
        logger.info("callback_registered", total_callbacks=len(self.callbacks))

    async def start(self, symbols: List[str]) -> None:
        """
        Start consuming feeds from all exchanges for given symbols.

        Args:
            symbols: List of trading pair symbols to subscribe to
        """
        self.running = True
        logger.info("feed_handler_starting", exchanges=len(self.exchanges), symbols=len(symbols))

        for exchange_name, exchange in self.exchanges.items():
            for symbol in symbols:
                # Subscribe to order book updates
                try:
                    await exchange.subscribe_order_book(symbol)
                    logger.info(
                        "subscribed_to_feed",
                        exchange=exchange_name,
                        symbol=symbol,
                    )

                    # Create task to consume updates
                    task = asyncio.create_task(
                        self._consume_feed(exchange_name, exchange, symbol)
                    )
                    self.tasks.append(task)

                except Exception as e:
                    logger.error(
                        "subscription_failed",
                        exchange=exchange_name,
                        symbol=symbol,
                        error=str(e),
                    )

        logger.info("feed_handler_started", active_feeds=len(self.tasks))

    async def stop(self) -> None:
        """Stop all feed handlers."""
        logger.info("feed_handler_stopping", active_feeds=len(self.tasks))
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks.clear()
        logger.info(
            "feed_handler_stopped",
            updates_received=self.updates_received,
            updates_failed=self.updates_failed,
        )

    async def _consume_feed(
        self, exchange_name: str, exchange: BaseExchange, symbol: str
    ) -> None:
        """
        Consume WebSocket feed for a specific exchange and symbol.

        Args:
            exchange_name: Exchange name
            exchange: Exchange instance
            symbol: Trading pair symbol
        """
        consecutive_failures = 0
        max_consecutive_failures = 10

        while self.running:
            try:
                # Check if WebSocket manager exists
                if not hasattr(exchange, "_ws_manager") or not exchange._ws_manager:
                    logger.warning(
                        "websocket_not_available",
                        exchange=exchange_name,
                        symbol=symbol,
                    )
                    await asyncio.sleep(5)
                    continue

                # Receive order book update from WebSocket
                # Note: This is a simplified version. Real implementation would need
                # exchange-specific parsing based on their WebSocket message format
                update = await self._receive_update(exchange, symbol)

                if update:
                    await self._process_update(exchange_name, symbol, update)
                    consecutive_failures = 0
                    self.updates_received += 1

            except asyncio.CancelledError:
                logger.info("feed_consumer_cancelled", exchange=exchange_name, symbol=symbol)
                break

            except Exception as e:
                consecutive_failures += 1
                self.updates_failed += 1

                logger.error(
                    "feed_consumption_error",
                    exchange=exchange_name,
                    symbol=symbol,
                    error=str(e),
                    consecutive_failures=consecutive_failures,
                )

                if consecutive_failures >= max_consecutive_failures:
                    logger.error(
                        "max_failures_reached",
                        exchange=exchange_name,
                        symbol=symbol,
                        action="stopping_feed",
                    )
                    break

                # Brief pause before retry
                await asyncio.sleep(min(consecutive_failures, 10))

    async def _receive_update(
        self, exchange: BaseExchange, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Receive update from exchange WebSocket.

        Args:
            exchange: Exchange instance
            symbol: Trading pair symbol

        Returns:
            Parsed update dictionary or None
        """
        try:
            # This is a placeholder. Real implementation would call
            # exchange._ws_manager.receive() and parse the message
            # For now, we'll return None to indicate WebSocket not fully implemented
            return None

        except asyncio.TimeoutError:
            # Timeout is normal, just return None
            return None

        except Exception as e:
            logger.debug("receive_update_error", symbol=symbol, error=str(e))
            return None

    async def _process_update(
        self, exchange_name: str, symbol: str, update: Dict[str, Any]
    ) -> None:
        """
        Process an order book update.

        Args:
            exchange_name: Exchange name
            symbol: Trading pair symbol
            update: Update dictionary with bids and asks
        """
        try:
            # Parse bids and asks from update
            bids = []
            asks = []

            if "bids" in update:
                bids = [
                    (Decimal(str(p)), Decimal(str(q)))
                    for p, q in update["bids"][:20]
                ]

            if "asks" in update:
                asks = [
                    (Decimal(str(p)), Decimal(str(q)))
                    for p, q in update["asks"][:20]
                ]

            # Update order book manager
            self.order_book_manager.update_order_book(
                exchange_name, symbol, bids, asks
            )

            # Cache in Redis
            await self.cache.set_order_book(
                exchange_name,
                symbol,
                {
                    "bids": [(str(p), str(q)) for p, q in bids],
                    "asks": [(str(p), str(q)) for p, q in asks],
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            # Trigger callbacks
            for callback in self.callbacks:
                try:
                    await callback(exchange_name, symbol, bids, asks)
                except Exception as e:
                    logger.error("callback_error", callback=str(callback), error=str(e))

        except Exception as e:
            logger.error(
                "process_update_failed",
                exchange=exchange_name,
                symbol=symbol,
                error=str(e),
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get feed handler statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "running": self.running,
            "active_feeds": len(self.tasks),
            "callbacks": len(self.callbacks),
            "updates_received": self.updates_received,
            "updates_failed": self.updates_failed,
            "success_rate": (
                self.updates_received / max(1, self.updates_received + self.updates_failed) * 100
            ),
        }
