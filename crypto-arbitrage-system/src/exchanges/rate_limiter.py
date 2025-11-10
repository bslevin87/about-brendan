"""
Rate limiter implementation using token bucket algorithm.

This module provides intelligent rate limiting for exchange API calls
to prevent hitting exchange rate limits and getting banned.
"""
import asyncio
import time
from typing import Optional

from src.core.logger import get_logger

logger = get_logger(__name__, component="rate_limiter")


class RateLimiter:
    """
    Token bucket rate limiter for exchange API calls.

    The token bucket algorithm allows for burst capacity while maintaining
    a maximum sustained rate. Tokens are added at a fixed rate, and requests
    consume tokens. If no tokens are available, requests wait.

    Features:
    - Per-exchange rate limiting
    - Burst capacity support
    - Automatic backoff on limit hits
    - Async/await compatible
    - Thread-safe for concurrent requests

    Example:
        >>> limiter = RateLimiter(requests_per_second=10, burst_size=20)
        >>> async with limiter:
        >>>     # Make API call here
        >>>     response = await make_api_call()
    """

    def __init__(
        self,
        requests_per_second: float,
        burst_size: Optional[int] = None,
        name: str = "default"
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum sustained requests per second
            burst_size: Maximum burst requests (default: 2x requests_per_second)
            name: Name for logging purposes (e.g., exchange name)
        """
        self.name = name
        self.rate = float(requests_per_second)
        self.burst_size = burst_size or int(requests_per_second * 2)
        self.tokens = float(self.burst_size)  # Start with full bucket
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

        # Statistics
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0

        logger.debug(
            "rate_limiter_initialized",
            name=self.name,
            rate=self.rate,
            burst_size=self.burst_size
        )

    async def _add_tokens(self) -> None:
        """
        Add tokens based on time elapsed since last update.

        Tokens are added at the rate of requests_per_second.
        The bucket cannot exceed burst_size.
        """
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.rate
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.

        This method blocks until enough tokens are available.

        Args:
            tokens: Number of tokens to acquire (default: 1)

        Example:
            >>> await limiter.acquire(2)  # Acquire 2 tokens
            >>> # Make API call that counts as 2 requests
        """
        if tokens > self.burst_size:
            logger.warning(
                "requested_tokens_exceed_burst",
                tokens=tokens,
                burst_size=self.burst_size,
                name=self.name
            )

        async with self.lock:
            while True:
                await self._add_tokens()

                if self.tokens >= tokens:
                    # Enough tokens available
                    self.tokens -= tokens
                    self.total_requests += 1
                    return

                # Not enough tokens, calculate wait time
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate

                self.total_waits += 1
                self.total_wait_time += wait_time

                logger.debug(
                    "rate_limit_waiting",
                    wait_time=wait_time,
                    tokens_available=self.tokens,
                    tokens_needed=tokens,
                    name=self.name
                )

        # Wait outside the lock to allow other coroutines to proceed
        await asyncio.sleep(wait_time)

    async def __aenter__(self) -> "RateLimiter":
        """
        Context manager entry - acquire one token.

        Example:
            >>> async with limiter:
            >>>     # Make API call
            >>>     await fetch_data()
        """
        await self.acquire(1)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - no cleanup needed."""
        pass

    def get_wait_time(self, tokens: int = 1) -> float:
        """
        Get estimated wait time for acquiring tokens.

        Args:
            tokens: Number of tokens

        Returns:
            Estimated wait time in seconds

        Example:
            >>> wait = limiter.get_wait_time(5)
            >>> print(f"Need to wait {wait:.2f} seconds")
        """
        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.rate

    def get_available_tokens(self) -> float:
        """
        Get number of tokens currently available.

        Returns:
            Number of available tokens
        """
        return self.tokens

    def get_statistics(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with statistics

        Example:
            >>> stats = limiter.get_statistics()
            >>> print(f"Total requests: {stats['total_requests']}")
            >>> print(f"Average wait time: {stats['avg_wait_time']:.3f}s")
        """
        avg_wait_time = (
            self.total_wait_time / self.total_waits
            if self.total_waits > 0
            else 0.0
        )

        return {
            "name": self.name,
            "rate": self.rate,
            "burst_size": self.burst_size,
            "current_tokens": self.tokens,
            "total_requests": self.total_requests,
            "total_waits": self.total_waits,
            "total_wait_time": self.total_wait_time,
            "avg_wait_time": avg_wait_time,
        }

    def reset_statistics(self) -> None:
        """Reset all statistics counters."""
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        logger.debug("rate_limiter_statistics_reset", name=self.name)

    def __repr__(self) -> str:
        """Return string representation of rate limiter."""
        return (
            f"RateLimiter(name='{self.name}', rate={self.rate}/s, "
            f"burst={self.burst_size}, tokens={self.tokens:.2f})"
        )


class MultiExchangeRateLimiter:
    """
    Manages rate limiters for multiple exchanges.

    This class provides a convenient way to manage separate rate limiters
    for different exchanges, each with their own limits.

    Example:
        >>> limiters = MultiExchangeRateLimiter()
        >>> limiters.add_exchange("kraken", requests_per_second=15)
        >>> limiters.add_exchange("binance", requests_per_second=20)
        >>>
        >>> async with limiters.get("kraken"):
        >>>     # Make Kraken API call
        >>>     await kraken_api_call()
    """

    def __init__(self) -> None:
        """Initialize multi-exchange rate limiter."""
        self.limiters: dict[str, RateLimiter] = {}
        logger.debug("multi_exchange_rate_limiter_initialized")

    def add_exchange(
        self,
        name: str,
        requests_per_second: float,
        burst_size: Optional[int] = None
    ) -> None:
        """
        Add rate limiter for an exchange.

        Args:
            name: Exchange name
            requests_per_second: Rate limit for this exchange
            burst_size: Optional burst capacity
        """
        self.limiters[name] = RateLimiter(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            name=name
        )
        logger.info(
            "exchange_rate_limiter_added",
            exchange=name,
            rate=requests_per_second
        )

    def get(self, name: str) -> RateLimiter:
        """
        Get rate limiter for an exchange.

        Args:
            name: Exchange name

        Returns:
            RateLimiter instance

        Raises:
            KeyError: If exchange not found
        """
        if name not in self.limiters:
            raise KeyError(f"No rate limiter configured for exchange '{name}'")
        return self.limiters[name]

    def get_all_statistics(self) -> dict[str, dict]:
        """
        Get statistics for all exchanges.

        Returns:
            Dictionary mapping exchange names to their statistics
        """
        return {
            name: limiter.get_statistics()
            for name, limiter in self.limiters.items()
        }

    def reset_all_statistics(self) -> None:
        """Reset statistics for all exchanges."""
        for limiter in self.limiters.values():
            limiter.reset_statistics()
        logger.debug("all_rate_limiter_statistics_reset")
