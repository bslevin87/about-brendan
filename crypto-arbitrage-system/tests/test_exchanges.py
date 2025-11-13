"""
Tests for exchange integration components.

Tests rate limiter, WebSocket manager, and Kraken adapter.
"""
import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.base import MockExchange
from src.exchanges.exceptions import (
    AuthenticationError,
    InsufficientFundsError,
    InvalidSymbolError,
    RateLimitExceeded,
)
from src.exchanges.models import Balance, Order, OrderBook, Ticker, Trade
from src.exchanges.rate_limiter import RateLimiter
from src.exchanges.websocket_manager import WebSocketManager


# ==================== Rate Limiter Tests ====================


class TestRateLimiter:
    """Test rate limiter functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting."""
        limiter = RateLimiter(requests_per_second=10, burst_size=20)

        # Should allow immediate acquisition
        start = time.time()
        await limiter.acquire(1)
        elapsed = time.time() - start

        assert elapsed < 0.1  # Should be instant

    @pytest.mark.asyncio
    async def test_rate_limiter_burst(self):
        """Test burst capacity."""
        limiter = RateLimiter(requests_per_second=10, burst_size=20)

        # Consume all burst tokens
        for _ in range(20):
            await limiter.acquire(1)

        # Next acquisition should block
        start = time.time()
        await limiter.acquire(1)
        elapsed = time.time() - start

        assert elapsed >= 0.09  # Should wait ~0.1s for token

    @pytest.mark.asyncio
    async def test_rate_limiter_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        limiter = RateLimiter(requests_per_second=10, burst_size=20)

        await limiter.acquire(5)
        stats = limiter.get_statistics()

        # Acquiring 5 tokens counts as 1 request
        assert stats["total_requests"] == 1
        # But current_tokens should be reduced by 5
        assert stats["current_tokens"] == 15  # 20 - 5

    @pytest.mark.asyncio
    async def test_rate_limiter_context_manager(self):
        """Test using rate limiter as context manager."""
        limiter = RateLimiter(requests_per_second=10, burst_size=20)

        async with limiter:
            pass  # Should acquire and track

        stats = limiter.get_statistics()
        assert stats["total_requests"] >= 1

    @pytest.mark.asyncio
    async def test_rate_limiter_stats(self):
        """Test statistics tracking."""
        limiter = RateLimiter(requests_per_second=10, burst_size=5)

        # Consume some tokens
        for _ in range(5):
            await limiter.acquire(1)

        stats = limiter.get_statistics()
        assert stats["rate"] == 10
        assert stats["burst_size"] == 5
        assert stats["total_requests"] >= 5

    @pytest.mark.asyncio
    async def test_rate_limiter_refill(self):
        """Test token refill over time."""
        limiter = RateLimiter(requests_per_second=100, burst_size=10)  # 100/s = 0.01s per token

        # Consume all tokens
        for _ in range(10):
            await limiter.acquire(1)

        # Wait for refill
        await asyncio.sleep(0.2)  # Should refill ~20 tokens

        # Should be able to acquire immediately
        start = time.time()
        await limiter.acquire(5)
        elapsed = time.time() - start

        assert elapsed < 0.05  # Should be instant due to refill


# ==================== WebSocket Manager Tests ====================


class TestWebSocketManager:
    """Test WebSocket manager functionality."""

    @pytest.mark.asyncio
    async def test_websocket_manager_creation(self):
        """Test WebSocket manager initialization."""
        ws_manager = WebSocketManager(
            url="wss://test.example.com", name="test"
        )

        assert ws_manager.url == "wss://test.example.com"
        assert ws_manager.name == "test"
        assert not ws_manager.is_connected

    @pytest.mark.asyncio
    async def test_websocket_subscribe_unsubscribe(self):
        """Test subscription management."""
        ws_manager = WebSocketManager(
            url="wss://test.example.com", name="test"
        )

        # Simulate subscription
        await ws_manager.subscribe("orderbook", "BTC/USD")

        assert ("orderbook", "BTC/USD") in ws_manager._subscriptions

        # Simulate unsubscribe
        await ws_manager.unsubscribe("orderbook", "BTC/USD")

        assert ("orderbook", "BTC/USD") not in ws_manager._subscriptions


# ==================== Exchange Models Tests ====================


class TestExchangeModels:
    """Test exchange data models."""

    def test_order_book_properties(self):
        """Test OrderBook calculated properties."""
        from datetime import datetime
        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0")), (Decimal("49900"), Decimal("2.0"))],
            asks=[(Decimal("50100"), Decimal("1.5")), (Decimal("50200"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        assert order_book.best_bid == (Decimal("50000"), Decimal("1.0"))
        assert order_book.best_ask == (Decimal("50100"), Decimal("1.5"))
        assert order_book.spread == Decimal("100")
        assert order_book.mid_price == Decimal("50050")

    def test_order_properties(self):
        """Test Order calculated properties."""
        from datetime import datetime
        order = Order(
            order_id="test123",
            exchange="test",
            symbol="BTC/USD",
            side="buy",
            order_type="limit",
            quantity=Decimal("1.0"),
            price=Decimal("50000"),
            filled_quantity=Decimal("0.5"),
            status="partially_filled",
            timestamp=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        assert order.remaining_quantity == Decimal("0.5")
        assert order.fill_percent == Decimal("50")
        assert order.is_open is True
        assert order.is_completed is False

    def test_balance_properties(self):
        """Test Balance calculated properties."""
        from datetime import datetime
        balance = Balance(
            exchange="test",
            currency="BTC",
            total=Decimal("10"),
            available=Decimal("8"),
            locked=Decimal("2"),
            timestamp=datetime.utcnow(),
        )

        assert balance.locked_percent == Decimal("20")

    def test_ticker_properties(self):
        """Test Ticker calculated properties."""
        from datetime import datetime
        ticker = Ticker(
            exchange="test",
            symbol="BTC/USD",
            bid=Decimal("50000"),
            ask=Decimal("50100"),
            last=Decimal("50050"),
            volume_24h=Decimal("1000"),
            timestamp=datetime.utcnow(),
        )

        assert ticker.spread == Decimal("100")
        assert ticker.mid_price == Decimal("50050")
        assert ticker.spread_percent > 0


# ==================== Mock Exchange Tests ====================


class TestMockExchange:
    """Test mock exchange implementation."""

    @pytest.mark.asyncio
    async def test_mock_exchange_connection(self):
        """Test mock exchange connect/disconnect."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        assert exchange.is_connected is True

        await exchange.disconnect()
        assert exchange.is_connected is False

    @pytest.mark.asyncio
    async def test_mock_exchange_health_check(self):
        """Test mock exchange health check."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        is_healthy = await exchange.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_mock_exchange_fetch_ticker(self):
        """Test mock exchange ticker fetching."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        ticker = await exchange.fetch_ticker("BTC/USD")

        assert ticker.exchange == "MockExchange"
        assert ticker.symbol == "BTC/USD"
        assert ticker.bid > 0
        assert ticker.ask > ticker.bid

    @pytest.mark.asyncio
    async def test_mock_exchange_fetch_order_book(self):
        """Test mock exchange order book fetching."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        order_book = await exchange.fetch_order_book("BTC/USD", depth=10)

        assert order_book.exchange == "MockExchange"
        assert order_book.symbol == "BTC/USD"
        assert len(order_book.bids) > 0
        assert len(order_book.asks) > 0

    @pytest.mark.asyncio
    async def test_mock_exchange_fetch_balances(self):
        """Test mock exchange balance fetching."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        balances = await exchange.fetch_balances()

        assert len(balances) > 0
        assert all(b.exchange == "MockExchange" for b in balances)

    @pytest.mark.asyncio
    async def test_mock_exchange_create_order_dry_run(self):
        """Test mock exchange order creation (dry run)."""
        config = {"name": "MockExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()
        order = await exchange.create_order(
            symbol="BTC/USD",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            dry_run=True,
        )

        assert order.exchange == "MockExchange"
        assert order.symbol == "BTC/USD"
        assert order.side == "buy"
        assert order.quantity == Decimal("0.1")


# ==================== Kraken Exchange Tests ====================


class TestKrakenExchange:
    """Test Kraken exchange adapter."""

    def test_kraken_symbol_normalization(self):
        """Test Kraken symbol normalization."""
        config = {
            "name": "Kraken",
            "api_url": "https://api.kraken.com",
            "ws_url": "wss://ws.kraken.com",
        }
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = KrakenExchange(config, rate_limiter)

        # Test known mappings
        assert exchange.normalize_symbol("XXBTZUSD") == "BTC/USD"
        assert exchange.normalize_symbol("XETHZUSD") == "ETH/USD"

        # Test denormalization
        assert exchange.denormalize_symbol("BTC/USD") == "XXBTZUSD"
        assert exchange.denormalize_symbol("ETH/USD") == "XETHZUSD"

    def test_kraken_currency_normalization(self):
        """Test Kraken currency code normalization."""
        config = {
            "name": "Kraken",
            "api_url": "https://api.kraken.com",
            "ws_url": "wss://ws.kraken.com",
        }
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = KrakenExchange(config, rate_limiter)

        assert exchange._normalize_currency("XXBT") == "XBT"
        assert exchange._normalize_currency("ZUSD") == "USD"
        assert exchange._normalize_currency("USD") == "USD"

    @pytest.mark.asyncio
    async def test_kraken_sign_request(self):
        """Test Kraken request signing."""
        config = {
            "name": "Kraken",
            "api_url": "https://api.kraken.com",
            "ws_url": "wss://ws.kraken.com",
        }
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = KrakenExchange(
            config, rate_limiter, api_key="test_key", api_secret="dGVzdF9zZWNyZXQ="
        )

        params = {"test": "value"}
        headers = await exchange._sign_request("/private/Balance", params)

        assert "API-Key" in headers
        assert "API-Sign" in headers
        assert headers["API-Key"] == "test_key"
        assert "nonce" in params

    @pytest.mark.asyncio
    async def test_kraken_error_mapping(self):
        """Test Kraken error message mapping."""
        config = {
            "name": "Kraken",
            "api_url": "https://api.kraken.com",
            "ws_url": "wss://ws.kraken.com",
        }
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = KrakenExchange(config, rate_limiter)

        # Test authentication error
        error = exchange._map_kraken_error("EAPI:Invalid key")
        assert isinstance(error, AuthenticationError)

        # Test rate limit error
        error = exchange._map_kraken_error("EORDER:Rate limit exceeded")
        assert isinstance(error, RateLimitExceeded)

        # Test insufficient funds
        error = exchange._map_kraken_error("EGeneral:Insufficient funds")
        assert isinstance(error, InsufficientFundsError)

        # Test invalid symbol
        error = exchange._map_kraken_error("EQuery:Unknown asset pair")
        assert isinstance(error, InvalidSymbolError)

    @pytest.mark.asyncio
    async def test_kraken_create_order_dry_run(self):
        """Test Kraken order creation in dry run mode."""
        config = {
            "name": "Kraken",
            "api_url": "https://api.kraken.com",
            "ws_url": "wss://ws.kraken.com",
        }
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = KrakenExchange(config, rate_limiter)

        # Don't connect to real API, just test dry_run order creation
        order = await exchange.create_order(
            symbol="BTC/USD",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            dry_run=True,
        )

        assert order.exchange == "Kraken"
        assert order.symbol == "BTC/USD"
        assert order.status == "pending"
        assert "DRYRUN" in order.order_id


# ==================== Integration Tests ====================


class TestExchangeIntegration:
    """Test exchange integration scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_exchanges_simultaneously(self):
        """Test using multiple exchanges at once."""
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)

        # Create multiple mock exchanges
        exchanges = []
        for i in range(3):
            config = {"name": f"Exchange{i}", "api_url": f"http://test{i}.com"}
            exchange = MockExchange(config, rate_limiter)
            await exchange.connect()
            exchanges.append(exchange)

        # Fetch tickers from all
        tickers = await asyncio.gather(
            *[ex.fetch_ticker("BTC/USD") for ex in exchanges]
        )

        assert len(tickers) == 3
        assert all(t.symbol == "BTC/USD" for t in tickers)

        # Disconnect all
        await asyncio.gather(*[ex.disconnect() for ex in exchanges])

    @pytest.mark.asyncio
    async def test_rate_limiting_across_requests(self):
        """Test rate limiting with multiple requests."""
        limiter = RateLimiter(requests_per_second=10, burst_size=5)
        config = {"name": "TestExchange", "api_url": "http://test.com"}
        exchange = MockExchange(config, limiter)

        await exchange.connect()

        # Make multiple requests
        start = time.time()
        for _ in range(10):
            async with limiter:
                await exchange.fetch_ticker("BTC/USD")

        elapsed = time.time() - start

        # Should take at least 0.5s due to rate limiting (5 tokens burst + 5 more at 10/s)
        assert elapsed >= 0.4

        await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_order_lifecycle(self):
        """Test complete order lifecycle."""
        config = {"name": "TestExchange", "api_url": "http://test.com"}
        rate_limiter = RateLimiter(requests_per_second=10, burst_size=20)
        exchange = MockExchange(config, rate_limiter)

        await exchange.connect()

        # Create order
        order = await exchange.create_order(
            symbol="BTC/USD",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            dry_run=True,
        )

        assert order.status == "open"

        # Fetch order
        fetched = await exchange.fetch_order(order.order_id, "BTC/USD")
        assert fetched.order_id == order.order_id

        # Cancel order
        cancelled = await exchange.cancel_order(order.order_id, "BTC/USD")
        assert cancelled is True

        await exchange.disconnect()
