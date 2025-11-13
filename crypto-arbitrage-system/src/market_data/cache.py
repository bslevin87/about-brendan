"""
Redis cache manager for market data.

Provides high-performance caching for:
- Order books
- Tickers
- Arbitrage opportunities
- Exchange health status
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from src.core.logger import get_logger

logger = get_logger(__name__, component="cache")


class MarketDataCache:
    """
    Redis-backed cache for real-time market data.

    Stores:
    - Latest order books (per exchange, per symbol)
    - Latest tickers
    - Recent opportunities
    - Exchange health status
    """

    def __init__(self, redis_url: str) -> None:
        """
        Initialize cache manager.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        """
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.redis = await redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis.ping()
            logger.info("redis_connected", url=self.redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("redis_disconnected")

    # ==================== Order Book Operations ====================

    async def set_order_book(
        self, exchange: str, symbol: str, order_book: Dict[str, Any], ttl: int = 60
    ) -> None:
        """
        Store order book with TTL.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            order_book: Order book data
            ttl: Time to live in seconds
        """
        if not self.redis:
            return

        key = f"orderbook:{exchange}:{symbol}"
        try:
            await self.redis.setex(key, ttl, json.dumps(order_book, default=str))
        except Exception as e:
            logger.error(
                "cache_set_order_book_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )

    async def get_order_book(
        self, exchange: str, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve order book.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Order book data or None if not found
        """
        if not self.redis:
            return None

        key = f"orderbook:{exchange}:{symbol}"
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(
                "cache_get_order_book_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )
            return None

    # ==================== Ticker Operations ====================

    async def set_ticker(
        self, exchange: str, symbol: str, ticker: Dict[str, Any], ttl: int = 10
    ) -> None:
        """
        Store ticker with TTL.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            ticker: Ticker data
            ttl: Time to live in seconds
        """
        if not self.redis:
            return

        key = f"ticker:{exchange}:{symbol}"
        try:
            await self.redis.setex(key, ttl, json.dumps(ticker, default=str))
        except Exception as e:
            logger.error(
                "cache_set_ticker_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )

    async def get_ticker(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve ticker.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Ticker data or None if not found
        """
        if not self.redis:
            return None

        key = f"ticker:{exchange}:{symbol}"
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(
                "cache_get_ticker_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )
            return None

    # ==================== Opportunity Operations ====================

    async def store_opportunity(
        self, opportunity: Dict[str, Any], ttl: int = 300
    ) -> None:
        """
        Store detected opportunity.

        Args:
            opportunity: Opportunity data
            ttl: Time to live in seconds
        """
        if not self.redis:
            return

        opportunity_id = opportunity["opportunity_id"]
        key = f"opportunity:{opportunity_id}"

        try:
            await self.redis.setex(key, ttl, json.dumps(opportunity, default=str))

            # Also add to sorted set by profit (for ranking)
            await self.redis.zadd(
                "opportunities:by_profit",
                {opportunity_id: float(opportunity["net_profit_percent"])},
            )

            logger.debug(
                "opportunity_cached",
                opportunity_id=opportunity_id,
                profit=opportunity["net_profit_percent"],
            )
        except Exception as e:
            logger.error(
                "cache_store_opportunity_failed",
                opportunity_id=opportunity_id,
                error=str(e),
            )

    async def get_opportunity(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve opportunity by ID.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            Opportunity data or None if not found
        """
        if not self.redis:
            return None

        key = f"opportunity:{opportunity_id}"
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(
                "cache_get_opportunity_failed",
                opportunity_id=opportunity_id,
                error=str(e),
            )
            return None

    async def get_top_opportunities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top opportunities by profit.

        Args:
            limit: Maximum number of opportunities to return

        Returns:
            List of opportunity data dictionaries
        """
        if not self.redis:
            return []

        try:
            # Get top N opportunity IDs from sorted set
            opportunity_ids = await self.redis.zrevrange(
                "opportunities:by_profit", 0, limit - 1
            )

            opportunities = []
            for opp_id in opportunity_ids:
                key = f"opportunity:{opp_id}"
                data = await self.redis.get(key)
                if data:
                    opportunities.append(json.loads(data))

            return opportunities
        except Exception as e:
            logger.error("cache_get_top_opportunities_failed", error=str(e))
            return []

    async def clear_expired_opportunities(self) -> int:
        """
        Clear expired opportunities from sorted set.

        Returns:
            Number of opportunities cleared
        """
        if not self.redis:
            return 0

        try:
            # Get all opportunity IDs
            all_ids = await self.redis.zrange("opportunities:by_profit", 0, -1)

            removed = 0
            for opp_id in all_ids:
                key = f"opportunity:{opp_id}"
                # Check if key still exists (TTL expired means it's gone)
                exists = await self.redis.exists(key)
                if not exists:
                    # Remove from sorted set
                    await self.redis.zrem("opportunities:by_profit", opp_id)
                    removed += 1

            if removed > 0:
                logger.debug("expired_opportunities_cleared", count=removed)

            return removed
        except Exception as e:
            logger.error("cache_clear_expired_opportunities_failed", error=str(e))
            return 0

    # ==================== Exchange Health ====================

    async def set_exchange_health(
        self, exchange: str, is_healthy: bool, latency_ms: float
    ) -> None:
        """
        Store exchange health status.

        Args:
            exchange: Exchange name
            is_healthy: Health status
            latency_ms: Latency in milliseconds
        """
        if not self.redis:
            return

        key = f"health:{exchange}"
        data = {
            "healthy": is_healthy,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            await self.redis.setex(key, 60, json.dumps(data))
        except Exception as e:
            logger.error(
                "cache_set_exchange_health_failed", exchange=exchange, error=str(e)
            )

    async def get_exchange_health(self, exchange: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve exchange health status.

        Args:
            exchange: Exchange name

        Returns:
            Health data or None if not found
        """
        if not self.redis:
            return None

        key = f"health:{exchange}"
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(
                "cache_get_exchange_health_failed", exchange=exchange, error=str(e)
            )
            return None

    async def get_all_exchange_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health status for all exchanges.

        Returns:
            Dictionary mapping exchange names to health data
        """
        if not self.redis:
            return {}

        try:
            # Find all health keys
            keys = await self.redis.keys("health:*")
            health_data = {}

            for key in keys:
                exchange = key.split(":")[1]
                data = await self.redis.get(key)
                if data:
                    health_data[exchange] = json.loads(data)

            return health_data
        except Exception as e:
            logger.error("cache_get_all_exchange_health_failed", error=str(e))
            return {}

    # ==================== Statistics ====================

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        if not self.redis:
            return {}

        try:
            info = await self.redis.info()
            dbsize = await self.redis.dbsize()

            return {
                "connected": True,
                "keys": dbsize,
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
            }
        except Exception as e:
            logger.error("cache_get_stats_failed", error=str(e))
            return {"connected": False, "error": str(e)}
