"""
Tests for P&L tracker.

Tests:
- Trade recording
- Period resets (hourly/daily)
- Win rate calculations
- Consecutive streaks
- Performance metrics
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.risk.pnl_tracker import PnLTracker


class TestPnLTracker:
    """Test P&L tracking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = PnLTracker()

    def test_initialization(self):
        """Test tracker initialization."""
        assert self.tracker.daily_pnl == Decimal("0")
        assert self.tracker.hourly_pnl == Decimal("0")
        assert self.tracker.total_pnl == Decimal("0")
        assert self.tracker.consecutive_wins == 0
        assert self.tracker.consecutive_losses == 0

    def test_record_winning_trade(self):
        """Test recording a winning trade."""
        self.tracker.record_trade(Decimal("100"), {"symbol": "BTC/USD"})

        assert self.tracker.total_pnl == Decimal("100")
        assert self.tracker.daily_pnl == Decimal("100")
        assert self.tracker.hourly_pnl == Decimal("100")
        assert self.tracker.consecutive_wins == 1
        assert self.tracker.consecutive_losses == 0

    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        self.tracker.record_trade(Decimal("-50"), {"symbol": "ETH/USD"})

        assert self.tracker.total_pnl == Decimal("-50")
        assert self.tracker.consecutive_wins == 0
        assert self.tracker.consecutive_losses == 1

    def test_consecutive_wins(self):
        """Test consecutive wins tracking."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("50"))
        self.tracker.record_trade(Decimal("75"))

        assert self.tracker.consecutive_wins == 3
        assert self.tracker.consecutive_losses == 0

    def test_consecutive_losses(self):
        """Test consecutive losses tracking."""
        self.tracker.record_trade(Decimal("-100"))
        self.tracker.record_trade(Decimal("-50"))
        self.tracker.record_trade(Decimal("-25"))

        assert self.tracker.consecutive_wins == 0
        assert self.tracker.consecutive_losses == 3

    def test_consecutive_streak_reset(self):
        """Test consecutive streak resets on opposite outcome."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("50"))
        assert self.tracker.consecutive_wins == 2

        # Loss resets win streak
        self.tracker.record_trade(Decimal("-25"))
        assert self.tracker.consecutive_wins == 0
        assert self.tracker.consecutive_losses == 1

    def test_get_win_rate_empty(self):
        """Test win rate with no trades."""
        assert self.tracker.get_win_rate() == Decimal("0")

    def test_get_win_rate(self):
        """Test win rate calculation."""
        self.tracker.record_trade(Decimal("100"))  # Win
        self.tracker.record_trade(Decimal("50"))  # Win
        self.tracker.record_trade(Decimal("-25"))  # Loss
        self.tracker.record_trade(Decimal("75"))  # Win

        # 3 wins out of 4 = 75%
        assert self.tracker.get_win_rate() == Decimal("75")

    def test_get_average_profit(self):
        """Test average profit calculation."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("50"))
        self.tracker.record_trade(Decimal("-30"))
        self.tracker.record_trade(Decimal("80"))

        # Average = (100 + 50 - 30 + 80) / 4 = 50
        assert self.tracker.get_average_profit() == Decimal("50")

    def test_get_total_wins(self):
        """Test total wins count."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("-50"))
        self.tracker.record_trade(Decimal("75"))

        assert self.tracker.get_total_wins() == 2

    def test_get_total_losses(self):
        """Test total losses count."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("-50"))
        self.tracker.record_trade(Decimal("-25"))

        assert self.tracker.get_total_losses() == 2

    def test_get_largest_win(self):
        """Test largest win calculation."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("250"))
        self.tracker.record_trade(Decimal("50"))

        assert self.tracker.get_largest_win() == Decimal("250")

    def test_get_largest_loss(self):
        """Test largest loss calculation."""
        self.tracker.record_trade(Decimal("-100"))
        self.tracker.record_trade(Decimal("-250"))
        self.tracker.record_trade(Decimal("-50"))

        assert self.tracker.get_largest_loss() == Decimal("-250")

    def test_hourly_reset_manual(self):
        """Test manual hourly period reset."""
        self.tracker.record_trade(Decimal("100"))
        assert self.tracker.hourly_pnl == Decimal("100")

        # Simulate hour passing
        self.tracker.last_hourly_reset = datetime.utcnow() - timedelta(hours=2)
        self.tracker.check_and_reset_periods()

        # Hourly should reset, but total should remain
        assert self.tracker.hourly_pnl == Decimal("0")
        assert self.tracker.total_pnl == Decimal("100")

    def test_daily_reset_manual(self):
        """Test manual daily period reset."""
        self.tracker.record_trade(Decimal("100"))
        assert self.tracker.daily_pnl == Decimal("100")

        # Simulate day passing
        self.tracker.last_daily_reset = datetime.utcnow() - timedelta(days=2)
        self.tracker.check_and_reset_periods()

        # Daily should reset, but total should remain
        assert self.tracker.daily_pnl == Decimal("0")
        assert self.tracker.total_pnl == Decimal("100")

    def test_get_stats(self):
        """Test comprehensive stats retrieval."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("-50"))
        self.tracker.record_trade(Decimal("75"))

        stats = self.tracker.get_stats()

        assert stats["total_trades"] == 3
        assert stats["total_wins"] == 2
        assert stats["total_losses"] == 1
        assert stats["total_pnl_usd"] == 125.0
        assert stats["win_rate_percent"] > 0

    def test_reset_all(self):
        """Test complete reset."""
        self.tracker.record_trade(Decimal("100"))
        self.tracker.record_trade(Decimal("50"))

        self.tracker.reset_all()

        assert self.tracker.total_pnl == Decimal("0")
        assert self.tracker.daily_pnl == Decimal("0")
        assert self.tracker.hourly_pnl == Decimal("0")
        assert self.tracker.consecutive_wins == 0
        assert self.tracker.consecutive_losses == 0
        assert len(self.tracker.completed_trades) == 0
