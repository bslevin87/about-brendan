"""
Tests for position tracker.

Tests:
- Position adding/removing
- Exposure calculations
- Position counting
- P&L calculations
"""
import pytest
from decimal import Decimal
from src.risk.position_tracker import PositionTracker


class TestPositionTracker:
    """Test position tracking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = PositionTracker()

    def test_initialization(self):
        """Test tracker initialization."""
        assert self.tracker.get_total_position_count() == 0
        assert self.tracker.get_total_exposure() == Decimal("0")

    def test_add_position(self):
        """Test adding a position."""
        self.tracker.add_position(
            position_id="pos1",
            exchange="Kraken",
            symbol="BTC/USD",
            side="long",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
        )

        assert self.tracker.get_total_position_count() == 1
        position = self.tracker.get_position("pos1")
        assert position is not None
        assert position.exchange == "Kraken"
        assert position.symbol == "BTC/USD"
        assert position.side == "long"
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000")

    def test_remove_position(self):
        """Test removing a position."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        assert self.tracker.get_total_position_count() == 1

        removed = self.tracker.remove_position("pos1")
        assert removed is not None
        assert self.tracker.get_total_position_count() == 0

    def test_get_positions_by_exchange(self):
        """Test getting positions by exchange."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )
        self.tracker.add_position(
            "pos3", "Kraken", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )

        kraken_positions = self.tracker.get_positions_by_exchange("Kraken")
        assert len(kraken_positions) == 2

        coinbase_positions = self.tracker.get_positions_by_exchange("Coinbase Advanced")
        assert len(coinbase_positions) == 1

    def test_get_positions_by_symbol(self):
        """Test getting positions by symbol."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos3", "Kraken", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )

        btc_positions = self.tracker.get_positions_by_symbol("BTC/USD")
        assert len(btc_positions) == 2

        eth_positions = self.tracker.get_positions_by_symbol("ETH/USD")
        assert len(eth_positions) == 1

    def test_get_total_exposure(self):
        """Test total exposure calculation."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        # Exposure = 0.1 * 50000 = 5000
        assert self.tracker.get_total_exposure() == Decimal("5000")

        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )
        # Total exposure = 5000 + 3000 = 8000
        assert self.tracker.get_total_exposure() == Decimal("8000")

    def test_get_exposure_by_exchange(self):
        """Test exposure calculation by exchange."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Kraken", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )
        self.tracker.add_position(
            "pos3", "Coinbase Advanced", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )

        kraken_exposure = self.tracker.get_exposure_by_exchange("Kraken")
        assert kraken_exposure == Decimal("8000")  # 5000 + 3000

        coinbase_exposure = self.tracker.get_exposure_by_exchange("Coinbase Advanced")
        assert coinbase_exposure == Decimal("5000")

    def test_get_exposure_by_symbol(self):
        """Test exposure calculation by symbol."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )

        btc_exposure = self.tracker.get_exposure_by_symbol("BTC/USD")
        assert btc_exposure == Decimal("10000")  # 5000 + 5000

    def test_update_position_price_long(self):
        """Test updating position price for long position."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )

        # Price goes up
        self.tracker.update_position_price("pos1", Decimal("51000"))
        position = self.tracker.get_position("pos1")

        # P&L = (51000 - 50000) * 0.1 = 100
        assert position.unrealized_pnl_usd == Decimal("100")
        assert position.pnl_percent == Decimal("2")  # 2% gain

    def test_update_position_price_short(self):
        """Test updating position price for short position."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "short", Decimal("0.1"), Decimal("50000")
        )

        # Price goes up (loss for short)
        self.tracker.update_position_price("pos1", Decimal("51000"))
        position = self.tracker.get_position("pos1")

        # P&L = (50000 - 51000) * 0.1 = -100
        assert position.unrealized_pnl_usd == Decimal("-100")
        assert position.pnl_percent == Decimal("-2")  # 2% loss

    def test_get_total_unrealized_pnl(self):
        """Test total unrealized P&L calculation."""
        # Add two positions
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )

        # Update prices
        self.tracker.update_position_price("pos1", Decimal("51000"))  # +100
        self.tracker.update_position_price("pos2", Decimal("3100"))  # +100

        total_pnl = self.tracker.get_total_unrealized_pnl()
        assert total_pnl == Decimal("200")

    def test_clear_all_positions(self):
        """Test clearing all positions."""
        self.tracker.add_position(
            "pos1", "Kraken", "BTC/USD", "long", Decimal("0.1"), Decimal("50000")
        )
        self.tracker.add_position(
            "pos2", "Coinbase Advanced", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
        )

        assert self.tracker.get_total_position_count() == 2

        count = self.tracker.clear_all_positions()
        assert count == 2
        assert self.tracker.get_total_position_count() == 0
