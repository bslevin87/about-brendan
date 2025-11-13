"""
Market data aggregator.

Central coordinator for market data collection, processing, and
opportunity detection across all exchanges.
"""
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.market_data.cache import MarketDataCache
from src.market_data.feed_handler import FeedHandler
from src.market_data.order_book_manager import OrderBookManager
from src.market_data.spread_calculator import SpreadCalculator

logger = get_logger(__name__, component="aggregator")


class MarketDataAggregator:
    """
    Central coordinator for market data.

    This is the main interface for the rest of the system to access market data.
    Coordinates order book management, spread calculation, WebSocket feeds,
    and Redis caching.
    """

    def __init__(
        self,
        exchanges: Dict[str, BaseExchange],
        config: Any,
        redis_url: str,
    ) -> None:
        """
        Initialize market data aggregator.

        Args:
            exchanges: Dictionary mapping exchange names to exchange instances
            config: Configuration manager
            redis_url: Redis connection URL
        """
        self.exchanges = exchanges
        self.config = config
        self.running = False

        # Initialize components
        self.cache = MarketDataCache(redis_url)
        self.order_book_manager = OrderBookManager()
        self.spread_calculator = SpreadCalculator(self.order_book_manager, config)
        self.feed_handler = FeedHandler(
            exchanges, self.order_book_manager, self.cache
        )

        # Background tasks
        self._tasks: List[asyncio.Task] = []

        logger.info(
            "aggregator_initialized",
            exchanges=len(exchanges),
            redis_url=redis_url,
        )

    async def start(self, symbols: List[str]) -> None:
        """
        Start aggregating market data for given symbols.

        Args:
            symbols: List of trading pair symbols to monitor
        """
        logger.info("aggregator_starting", symbols=symbols)

        try:
            # Connect to Redis
            await self.cache.connect()

            # Initialize order books (fetch snapshots)
            await self._initialize_order_books(symbols)

            # Start WebSocket feeds
            # Note: WebSocket functionality is prepared but may not work
            # until exchanges implement message parsing
            await self.feed_handler.start(symbols)

            # Start background tasks
            self._start_background_tasks()

            self.running = True
            logger.info(
                "aggregator_started",
                symbols=len(symbols),
                exchanges=len(self.exchanges),
            )

        except Exception as e:
            logger.error("aggregator_start_failed", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop aggregator and cleanup resources."""
        logger.info("aggregator_stopping")
        self.running = False

        # Stop feed handler
        await self.feed_handler.stop()

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Disconnect from Redis
        await self.cache.disconnect()

        logger.info("aggregator_stopped")

    async def _initialize_order_books(self, symbols: List[str]) -> None:
        """
        Fetch initial order book snapshots from all exchanges.

        Args:
            symbols: List of trading pair symbols
        """
        logger.info("initializing_order_books", symbols=len(symbols), exchanges=len(self.exchanges))

        for exchange_name, exchange in self.exchanges.items():
            for symbol in symbols:
                try:
                    # Fetch order book snapshot
                    order_book = await exchange.fetch_order_book(symbol, depth=50)

                    # Initialize in order book manager
                    self.order_book_manager.initialize_order_book(
                        exchange_name, symbol, order_book
                    )

                    # Cache in Redis
                    await self.cache.set_order_book(
                        exchange_name,
                        symbol,
                        {
                            "bids": [(str(p), str(q)) for p, q in order_book.bids[:20]],
                            "asks": [(str(p), str(q)) for p, q in order_book.asks[:20]],
                            "timestamp": order_book.timestamp.isoformat(),
                        },
                    )

                    logger.info(
                        "order_book_initialized",
                        exchange=exchange_name,
                        symbol=symbol,
                        bid_levels=len(order_book.bids),
                        ask_levels=len(order_book.asks),
                    )

                except Exception as e:
                    logger.error(
                        "order_book_init_failed",
                        exchange=exchange_name,
                        symbol=symbol,
                        error=str(e),
                    )

    def _start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        # Task to periodically clear expired opportunities from cache
        task = asyncio.create_task(self._cleanup_expired_opportunities())
        self._tasks.append(task)

        logger.debug("background_tasks_started", tasks=len(self._tasks))

    async def _cleanup_expired_opportunities(self) -> None:
        """Periodically clean up expired opportunities from cache."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Run every minute

                removed = await self.cache.clear_expired_opportunities()
                if removed > 0:
                    logger.debug("expired_opportunities_cleaned", count=removed)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cleanup_failed", error=str(e))

    def get_best_prices(self, symbol: str) -> Dict[str, Dict[str, Decimal]]:
        """
        Get best bid/ask from all exchanges for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary mapping exchange names to price data
        """
        prices = {}

        for exchange_name in self.exchanges.keys():
            best_bid = self.order_book_manager.get_best_bid(exchange_name, symbol)
            best_ask = self.order_book_manager.get_best_ask(exchange_name, symbol)

            if best_bid and best_ask:
                spread = best_ask[0] - best_bid[0]
                prices[exchange_name] = {
                    "bid": best_bid[0],
                    "ask": best_ask[0],
                    "spread": spread,
                    "bid_quantity": best_bid[1],
                    "ask_quantity": best_ask[1],
                }

        return prices

    def get_order_book(
        self, exchange: str, symbol: str, depth: int = 10
    ) -> Optional[Dict]:
        """
        Get order book snapshot.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            depth: Number of levels

        Returns:
            Order book snapshot or None
        """
        return self.order_book_manager.get_order_book_snapshot(exchange, symbol, depth)

    def find_arbitrage_opportunities(
        self, symbols: List[str], min_profit_percent: Decimal = Decimal("0.1")
    ) -> List[Dict]:
        """
        Find all arbitrage opportunities across configured strategies.

        Args:
            symbols: List of trading pair symbols to analyze
            min_profit_percent: Minimum profit threshold

        Returns:
            List of opportunity dictionaries sorted by profit
        """
        all_opportunities = []

        # Cross-exchange arbitrage
        for symbol in symbols:
            cross_ex_opps = self.spread_calculator.calculate_cross_exchange_spread(
                symbol, list(self.exchanges.keys())
            )

            # Filter by minimum profit
            filtered = [
                opp
                for opp in cross_ex_opps
                if opp["net_profit_percent"] >= min_profit_percent
            ]

            all_opportunities.extend(filtered)

        # Triangle arbitrage (per exchange)
        for exchange_name in self.exchanges.keys():
            triangle_opps = self.spread_calculator.find_triangle_arbitrage(
                exchange_name
            )

            # Filter by minimum profit
            filtered = [
                opp
                for opp in triangle_opps
                if opp["net_profit_percent"] >= min_profit_percent
            ]

            all_opportunities.extend(filtered)

        # Sort by net profit (descending)
        all_opportunities.sort(key=lambda x: x["net_profit_percent"], reverse=True)

        logger.debug(
            "opportunities_found",
            total=len(all_opportunities),
            symbols=len(symbols),
        )

        return all_opportunities

    def get_stats(self) -> Dict[str, Any]:
        """
        Get aggregator statistics.

        Returns:
            Dictionary with comprehensive statistics
        """
        return {
            "running": self.running,
            "exchanges": len(self.exchanges),
            "order_book_manager": self.order_book_manager.get_stats(),
            "feed_handler": self.feed_handler.get_stats(),
            "cache": self.cache.get_stats() if self.running else {},
        }

    async def refresh_order_books(self, symbols: List[str]) -> None:
        """
        Manually refresh order books from REST API.

        Useful when WebSocket feeds are not available or for periodic validation.

        Args:
            symbols: List of symbols to refresh
        """
        logger.info("refreshing_order_books", symbols=len(symbols))

        for exchange_name, exchange in self.exchanges.items():
            for symbol in symbols:
                try:
                    order_book = await exchange.fetch_order_book(symbol, depth=50)
                    self.order_book_manager.initialize_order_book(
                        exchange_name, symbol, order_book
                    )

                    logger.debug(
                        "order_book_refreshed",
                        exchange=exchange_name,
                        symbol=symbol,
                    )

                except Exception as e:
                    logger.error(
                        "order_book_refresh_failed",
                        exchange=exchange_name,
                        symbol=symbol,
                        error=str(e),
                    )
