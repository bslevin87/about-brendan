"""
Tests for spread calculator.

Tests cross-exchange spread calculation, triangle arbitrage detection,
fee calculations, and profit estimations.
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from src.exchanges.models import OrderBook
from src.market_data.order_book_manager import OrderBookManager
from src.market_data.spread_calculator import SpreadCalculator


class TestSpreadCalculator:
    """Test spread calculator functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = OrderBookManager()

        # Create a mock config with proper dict behavior
        exchanges_dict = {
            "exchange1": {
                "taker_fee": 0.001,  # 0.1%
                "maker_fee": 0.0005,
                "supported_pairs": ["BTC/USD", "ETH/BTC", "ETH/USD"],
            },
            "exchange2": {
                "taker_fee": 0.002,  # 0.2%
                "maker_fee": 0.001,
                "supported_pairs": ["BTC/USD", "ETH/USD"],
            },
        }

        self.config = MagicMock()
        self.config.exchanges = MagicMock()
        self.config.exchanges.get = lambda x: exchanges_dict.get(x)

        self.calculator = SpreadCalculator(self.manager, self.config)

    def test_cross_exchange_profitable(self):
        """Test detecting profitable cross-exchange opportunity."""
        # Set up order books with price difference
        ob1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("49000"), Decimal("1.0"))],  # Lower ask
            timestamp=datetime.utcnow(),
        )

        ob2 = OrderBook(
            exchange="exchange2",
            symbol="BTC/USD",
            bids=[(Decimal("50500"), Decimal("1.0"))],  # Higher bid
            asks=[(Decimal("50600"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", ob1)
        self.manager.initialize_order_book("exchange2", "BTC/USD", ob2)

        # Calculate spreads
        opportunities = self.calculator.calculate_cross_exchange_spread(
            "BTC/USD", ["exchange1", "exchange2"]
        )

        # Should find opportunity: buy on exchange1 @ 49000, sell on exchange2 @ 50500
        assert len(opportunities) > 0
        best_opp = opportunities[0]
        assert best_opp["buy_exchange"] == "exchange1"
        assert best_opp["sell_exchange"] == "exchange2"
        assert best_opp["net_profit_percent"] > 0

    def test_cross_exchange_no_opportunity(self):
        """Test when no profitable opportunity exists."""
        # Set up order books with no arbitrage
        ob1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        ob2 = OrderBook(
            exchange="exchange2",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", ob1)
        self.manager.initialize_order_book("exchange2", "BTC/USD", ob2)

        opportunities = self.calculator.calculate_cross_exchange_spread(
            "BTC/USD", ["exchange1", "exchange2"]
        )

        # No profitable opportunities (fees would eliminate any small spread)
        profitable = [o for o in opportunities if o["net_profit_percent"] > 0]
        assert len(profitable) == 0

    def test_fee_calculation(self):
        """Test that fees are correctly calculated and deducted."""
        ob1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("49000"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        ob2 = OrderBook(
            exchange="exchange2",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", ob1)
        self.manager.initialize_order_book("exchange2", "BTC/USD", ob2)

        opportunities = self.calculator.calculate_cross_exchange_spread(
            "BTC/USD", ["exchange1", "exchange2"]
        )

        if opportunities:
            opp = opportunities[0]
            # Fees should be deducted from gross profit
            assert opp["total_fees_percent"] > 0
            assert opp["net_profit_percent"] < opp["gross_profit_percent"]

    def test_insufficient_exchanges(self):
        """Test with insufficient exchanges."""
        ob1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", ob1)

        # Only one exchange, can't do cross-exchange
        opportunities = self.calculator.calculate_cross_exchange_spread(
            "BTC/USD", ["exchange1"]
        )

        assert len(opportunities) == 0

    def test_triangle_arbitrage_detection(self):
        """Test triangle arbitrage detection."""
        # Set up triangle: BTC/USD, ETH/BTC, ETH/USD
        # Prices that create arbitrage opportunity

        btc_usd = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50000"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        eth_btc = OrderBook(
            exchange="exchange1",
            symbol="ETH/BTC",
            bids=[(Decimal("0.04"), Decimal("10.0"))],
            asks=[(Decimal("0.04"), Decimal("10.0"))],
            timestamp=datetime.utcnow(),
        )

        eth_usd = OrderBook(
            exchange="exchange1",
            symbol="ETH/USD",
            bids=[(Decimal("2100"), Decimal("10.0"))],
            asks=[(Decimal("2100"), Decimal("10.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", btc_usd)
        self.manager.initialize_order_book("exchange1", "ETH/BTC", eth_btc)
        self.manager.initialize_order_book("exchange1", "ETH/USD", eth_usd)

        # Find triangle opportunities
        opportunities = self.calculator.find_triangle_arbitrage("exchange1")

        # Should detect triangle (may or may not be profitable after fees)
        assert isinstance(opportunities, list)

    def test_get_all_spreads(self):
        """Test getting spreads for all exchanges."""
        ob1 = OrderBook(
            exchange="exchange1",
            symbol="BTC/USD",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50100"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        ob2 = OrderBook(
            exchange="exchange2",
            symbol="BTC/USD",
            bids=[(Decimal("50050"), Decimal("1.0"))],
            asks=[(Decimal("50150"), Decimal("1.0"))],
            timestamp=datetime.utcnow(),
        )

        self.manager.initialize_order_book("exchange1", "BTC/USD", ob1)
        self.manager.initialize_order_book("exchange2", "BTC/USD", ob2)

        spreads = self.calculator.get_all_spreads(
            "BTC/USD", ["exchange1", "exchange2"]
        )

        assert len(spreads) == 2
        assert "exchange1" in spreads
        assert "exchange2" in spreads
        assert spreads["exchange1"]["spread"] == Decimal("100")
        assert spreads["exchange2"]["spread"] == Decimal("100")
