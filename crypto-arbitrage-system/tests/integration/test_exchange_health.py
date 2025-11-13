"""
Exchange connectivity and health tests.

Tests that all exchanges can connect and provide data.

Run with: pytest tests/integration/test_exchange_health.py -v
"""

import pytest
import asyncio
from decimal import Decimal

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter


@pytest.fixture(scope="module")
def config():
    """Get config manager"""
    return ConfigManager()


@pytest.fixture(scope="module")
def logger():
    """Get logger"""
    return get_logger(__name__)


@pytest.fixture(scope="module")
async def kraken_exchange(config, logger):
    """Initialize Kraken exchange"""
    exchange = KrakenExchange(
        config=config.exchanges.kraken,
        logger=logger,
        rate_limiter=RateLimiter(15, 20, "kraken")
    )

    await exchange.connect()

    yield exchange

    await exchange.disconnect()


@pytest.fixture(scope="module")
async def coinbase_exchange(config, logger):
    """Initialize Coinbase Advanced exchange"""
    exchange = CoinbaseAdvancedExchange(
        config=config.exchanges.coinbase_advanced,
        logger=logger,
        rate_limiter=RateLimiter(10, 15, "coinbase")
    )

    await exchange.connect()

    yield exchange

    await exchange.disconnect()


@pytest.mark.asyncio
class TestKrakenExchange:
    """Test Kraken exchange connectivity"""

    async def test_kraken_connects(self, kraken_exchange):
        """Test Kraken connection"""
        assert kraken_exchange is not None
        assert kraken_exchange.name == "Kraken"

    async def test_kraken_health_check(self, kraken_exchange):
        """Test Kraken health check"""
        health = await kraken_exchange.health_check()
        assert health is True

    async def test_kraken_fetch_ticker(self, kraken_exchange):
        """Test fetching ticker from Kraken"""
        ticker = await kraken_exchange.fetch_ticker("BTC/USD")

        assert ticker is not None
        assert hasattr(ticker, 'symbol')
        assert hasattr(ticker, 'bid')
        assert hasattr(ticker, 'ask')
        assert hasattr(ticker, 'last')

        assert ticker.symbol == "BTC/USD"
        assert ticker.bid > 0
        assert ticker.ask > 0
        assert ticker.last > 0
        assert ticker.ask >= ticker.bid

    async def test_kraken_fetch_order_book(self, kraken_exchange):
        """Test fetching order book from Kraken"""
        order_book = await kraken_exchange.fetch_order_book("BTC/USD", depth=10)

        assert order_book is not None
        assert hasattr(order_book, 'symbol')
        assert hasattr(order_book, 'bids')
        assert hasattr(order_book, 'asks')

        assert order_book.symbol == "BTC/USD"
        assert len(order_book.bids) > 0
        assert len(order_book.asks) > 0

        # Verify bids are sorted descending
        for i in range(len(order_book.bids) - 1):
            assert order_book.bids[i][0] >= order_book.bids[i + 1][0]

        # Verify asks are sorted ascending
        for i in range(len(order_book.asks) - 1):
            assert order_book.asks[i][0] <= order_book.asks[i + 1][0]

    async def test_kraken_symbol_normalization(self, kraken_exchange):
        """Test Kraken symbol normalization"""
        # Test to_exchange_symbol
        exchange_symbol = kraken_exchange._to_exchange_symbol("BTC/USD")
        assert exchange_symbol in ["XXBTZUSD", "XBTUSD"]

        # Test from_exchange_symbol
        standard_symbol = kraken_exchange._from_exchange_symbol(exchange_symbol)
        assert standard_symbol == "BTC/USD"


@pytest.mark.asyncio
class TestCoinbaseExchange:
    """Test Coinbase Advanced exchange connectivity"""

    async def test_coinbase_connects(self, coinbase_exchange):
        """Test Coinbase connection"""
        assert coinbase_exchange is not None
        assert coinbase_exchange.name == "Coinbase Advanced"

    async def test_coinbase_health_check(self, coinbase_exchange):
        """Test Coinbase health check"""
        health = await coinbase_exchange.health_check()
        assert health is True

    async def test_coinbase_fetch_ticker(self, coinbase_exchange):
        """Test fetching ticker from Coinbase"""
        ticker = await coinbase_exchange.fetch_ticker("BTC/USD")

        assert ticker is not None
        assert hasattr(ticker, 'symbol')
        assert hasattr(ticker, 'bid')
        assert hasattr(ticker, 'ask')
        assert hasattr(ticker, 'last')

        assert ticker.symbol == "BTC/USD"
        assert ticker.bid > 0
        assert ticker.ask > 0
        assert ticker.last > 0
        assert ticker.ask >= ticker.bid

    async def test_coinbase_fetch_order_book(self, coinbase_exchange):
        """Test fetching order book from Coinbase"""
        order_book = await coinbase_exchange.fetch_order_book("BTC/USD", depth=10)

        assert order_book is not None
        assert hasattr(order_book, 'symbol')
        assert hasattr(order_book, 'bids')
        assert hasattr(order_book, 'asks')

        assert order_book.symbol == "BTC/USD"
        assert len(order_book.bids) > 0
        assert len(order_book.asks) > 0

        # Verify bids are sorted descending
        for i in range(len(order_book.bids) - 1):
            assert order_book.bids[i][0] >= order_book.bids[i + 1][0]

        # Verify asks are sorted ascending
        for i in range(len(order_book.asks) - 1):
            assert order_book.asks[i][0] <= order_book.asks[i + 1][0]

    async def test_coinbase_symbol_normalization(self, coinbase_exchange):
        """Test Coinbase symbol normalization"""
        # Test to_exchange_symbol
        exchange_symbol = coinbase_exchange._to_exchange_symbol("BTC/USD")
        assert exchange_symbol == "BTC-USD"

        # Test from_exchange_symbol
        standard_symbol = coinbase_exchange._from_exchange_symbol(exchange_symbol)
        assert standard_symbol == "BTC/USD"


@pytest.mark.asyncio
class TestCrossExchangeComparison:
    """Test cross-exchange data consistency"""

    async def test_price_reasonableness(self, kraken_exchange, coinbase_exchange):
        """Test that prices are reasonable across exchanges"""
        kraken_ticker = await kraken_exchange.fetch_ticker("BTC/USD")
        coinbase_ticker = await coinbase_exchange.fetch_ticker("BTC/USD")

        # Prices should be relatively close (within 5%)
        kraken_mid = (kraken_ticker.bid + kraken_ticker.ask) / 2
        coinbase_mid = (coinbase_ticker.bid + coinbase_ticker.ask) / 2

        difference_percent = abs(kraken_mid - coinbase_mid) / kraken_mid * 100

        # Allow up to 5% difference (should be much less in practice)
        assert difference_percent < 5.0, f"Price difference too large: {difference_percent:.2f}%"

    async def test_spread_reasonableness(self, kraken_exchange, coinbase_exchange):
        """Test that spreads are reasonable"""
        kraken_ticker = await kraken_exchange.fetch_ticker("BTC/USD")
        coinbase_ticker = await coinbase_exchange.fetch_ticker("BTC/USD")

        # Calculate spread percentages
        kraken_spread = (kraken_ticker.ask - kraken_ticker.bid) / kraken_ticker.bid * 100
        coinbase_spread = (coinbase_ticker.ask - coinbase_ticker.bid) / coinbase_ticker.bid * 100

        # Spreads should be reasonable (< 1% for BTC/USD)
        assert kraken_spread < 1.0, f"Kraken spread too large: {kraken_spread:.3f}%"
        assert coinbase_spread < 1.0, f"Coinbase spread too large: {coinbase_spread:.3f}%"

    async def test_order_book_depth(self, kraken_exchange, coinbase_exchange):
        """Test that order books have sufficient depth"""
        kraken_book = await kraken_exchange.fetch_order_book("BTC/USD", depth=20)
        coinbase_book = await coinbase_exchange.fetch_order_book("BTC/USD", depth=20)

        # Should have at least 10 levels on each side
        assert len(kraken_book.bids) >= 10
        assert len(kraken_book.asks) >= 10
        assert len(coinbase_book.bids) >= 10
        assert len(coinbase_book.asks) >= 10
