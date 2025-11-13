"""
Tests for order book manager.

Tests order book initialization, updates, depth retrieval,
spread calculation, and slippage estimation.
"""
import pytest
from datetime import datetime
from decimal import Decimal

from src.exchanges.models import OrderBook
from src.market_data.order_book_manager import OrderBookManager


class TestOrderBookManager:
    """Test order book manager functionality."""

    def test_initialization(self):
        """Test order book manager initialization."""
        manager = OrderBookManager()
        assert len(manager.order_books) == 0
        assert manager._update_count == 0

    def test_initialize_order_book(self):
        """Test initializing an order book with snapshot."""
        manager = OrderBookManager()

        # Create order book snapshot
        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49900"), Decimal("2.0")),
            ],
            asks=[
                (Decimal("50100"), Decimal("1.5")),
                (Decimal("50200"), Decimal("1.0")),
            ],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        assert manager.has_order_book("test", "BTC/USD")
        assert "test" in manager.order_books
        assert "BTC/USD" in manager.order_books["test"]

    def test_get_best_bid(self):
        """Test getting best bid price."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49900"), Decimal("2.0")),
                (Decimal("49800"), Decimal("3.0")),
            ],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        best_bid = manager.get_best_bid("test", "BTC/USD")
        assert best_bid is not None
        assert best_bid[0] == Decimal("50000")  # Highest bid
        assert best_bid[1] == Decimal("1.0")

    def test_get_best_ask(self):
        """Test getting best ask price."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[
                (Decimal("50100"), Decimal("1.0")),
                (Decimal("50200"), Decimal("2.0")),
                (Decimal("50300"), Decimal("3.0")),
            ],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        best_ask = manager.get_best_ask("test", "BTC/USD")
        assert best_ask is not None
        assert best_ask[0] == Decimal("50100")  # Lowest ask
        assert best_ask[1] == Decimal("1.0")

    def test_get_spread(self):
        """Test spread calculation."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        spread = manager.get_spread("test", "BTC/USD")
        assert spread == Decimal("100")  # 50100 - 50000

    def test_get_mid_price(self):
        """Test mid price calculation."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        mid_price = manager.get_mid_price("test", "BTC/USD")
        assert mid_price == Decimal("50050")  # (50000 + 50100) / 2

    def test_update_order_book(self):
        """Test incremental order book updates."""
        manager = OrderBookManager()

        # Initialize
        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        # Update with new prices
        new_bids = [(Decimal("50050"), Decimal("2.0"))]
        new_asks = [(Decimal("50150"), Decimal("3.0"))]

        manager.update_order_book("test", "BTC/USD", new_bids, new_asks)

        # Check updated best bid/ask
        best_bid = manager.get_best_bid("test", "BTC/USD")
        assert best_bid[0] == Decimal("50050")  # New highest bid

        best_ask = manager.get_best_ask("test", "BTC/USD")
        assert best_ask[0] == Decimal("50100")  # Old ask is still lowest

    def test_remove_price_level(self):
        """Test removing price level with zero quantity."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49900"), Decimal("2.0")),
            ],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        # Remove top bid by setting quantity to 0
        manager.update_order_book(
            "test", "BTC/USD", [(Decimal("50000"), Decimal("0"))], []
        )

        # Best bid should now be 49900
        best_bid = manager.get_best_bid("test", "BTC/USD")
        assert best_bid[0] == Decimal("49900")

    def test_get_depth(self):
        """Test getting order book depth."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49900"), Decimal("2.0")),
                (Decimal("49800"), Decimal("3.0")),
            ],
            asks=[
                (Decimal("50100"), Decimal("1.0")),
                (Decimal("50200"), Decimal("2.0")),
                (Decimal("50300"), Decimal("3.0")),
            ],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        # Get buy depth (bids)
        buy_depth = manager.get_depth("test", "BTC/USD", "buy", depth=2)
        assert len(buy_depth) == 2
        assert buy_depth[0][0] == Decimal("50000")  # Highest first
        assert buy_depth[1][0] == Decimal("49900")

        # Get sell depth (asks)
        sell_depth = manager.get_depth("test", "BTC/USD", "sell", depth=2)
        assert len(sell_depth) == 2
        assert sell_depth[0][0] == Decimal("50100")  # Lowest first
        assert sell_depth[1][0] == Decimal("50200")

    def test_calculate_slippage_low(self):
        """Test slippage calculation with sufficient liquidity."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("10.0"))],
            asks=[(Decimal("50100"), Decimal("10.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        # Small order should have minimal slippage
        slippage = manager.calculate_slippage(
            "test", "BTC/USD", "buy", Decimal("1.0")
        )
        assert slippage < Decimal("0.1")  # Less than 0.1%

    def test_calculate_slippage_high(self):
        """Test slippage calculation with insufficient liquidity."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("0.1"))],
            asks=[
                (Decimal("50100"), Decimal("0.1")),
                (Decimal("50200"), Decimal("0.1")),
                (Decimal("50300"), Decimal("0.1")),
            ],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)

        # Large order should have higher slippage
        slippage = manager.calculate_slippage(
            "test", "BTC/USD", "sell", Decimal("0.2")
        )
        assert slippage > Decimal("0")  # Some slippage expected

    def test_empty_order_book(self):
        """Test handling of non-existent order book."""
        manager = OrderBookManager()

        best_bid = manager.get_best_bid("nonexistent", "BTC/USD")
        assert best_bid is None

        best_ask = manager.get_best_ask("nonexistent", "BTC/USD")
        assert best_ask is None

        spread = manager.get_spread("nonexistent", "BTC/USD")
        assert spread is None

    def test_get_stats(self):
        """Test statistics retrieval."""
        manager = OrderBookManager()

        order_book = OrderBook(
            exchange="test",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("test", "BTC/USD", order_book)
        manager.update_order_book("test", "BTC/USD", [], [])

        stats = manager.get_stats()
        assert stats["exchanges"] == 1
        assert stats["total_books"] == 1
        assert stats["updates_processed"] == 1

    def test_multiple_exchanges(self):
        """Test managing order books for multiple exchanges."""
        manager = OrderBookManager()

        # Initialize for exchange1
        order_book1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        # Initialize for exchange2
        order_book2 = OrderBook(
            exchange="exchange2",
            symbol="BTC/USD",
            bids=[(Decimal("50050"), Decimal("1.0"))],
            asks=[(Decimal("50150"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        manager.initialize_order_book("exchange1", "BTC/USD", order_book1)
        manager.initialize_order_book("exchange2", "BTC/USD", order_book2)

        # Check both exist
        assert manager.has_order_book("exchange1", "BTC/USD")
        assert manager.has_order_book("exchange2", "BTC/USD")

        # Check different prices
        bid1 = manager.get_best_bid("exchange1", "BTC/USD")
        bid2 = manager.get_best_bid("exchange2", "BTC/USD")
        assert bid1[0] != bid2[0]
