"""
Profit & Loss tracking system.

Tracks realized and unrealized P&L:
- Daily/hourly P&L monitoring
- Consecutive wins/losses tracking
- Trade success rate calculations
- Performance metrics (Sharpe ratio, average profit)
"""
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.core.logger import get_logger

logger = get_logger(__name__, component="pnl_tracker")


class PnLTracker:
    """
    Tracks realized and unrealized profit & loss.

    Monitors:
    - Daily/hourly P&L
    - Consecutive wins/losses
    - Trade success rate
    - Sharpe ratio
    """

    def __init__(self):
        """Initialize P&L tracker."""
        # P&L tracking
        self.daily_pnl = Decimal("0")
        self.hourly_pnl = Decimal("0")
        self.total_pnl = Decimal("0")

        # Trade history (for statistics)
        self.completed_trades: deque = deque(maxlen=1000)  # Last 1000 trades

        # Consecutive tracking
        self.consecutive_wins = 0
        self.consecutive_losses = 0

        # Time tracking for resets
        self.last_daily_reset = datetime.utcnow()
        self.last_hourly_reset = datetime.utcnow()

        logger.info("P&L tracker initialized")

    def record_trade(
        self, pnl_usd: Decimal, trade_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a completed trade.

        Args:
            pnl_usd: Profit/loss in USD
            trade_details: Additional trade information
        """
        # Update P&L
        self.daily_pnl += pnl_usd
        self.hourly_pnl += pnl_usd
        self.total_pnl += pnl_usd

        # Record trade
        trade_record = {
            "pnl_usd": pnl_usd,
            "timestamp": datetime.utcnow(),
            "is_profit": pnl_usd > 0,
            "details": trade_details or {},
        }
        self.completed_trades.append(trade_record)

        # Update consecutive streaks
        if pnl_usd > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        logger.info(
            "trade_recorded",
            pnl_usd=float(pnl_usd),
            daily_pnl=float(self.daily_pnl),
            total_pnl=float(self.total_pnl),
            consecutive_wins=self.consecutive_wins,
            consecutive_losses=self.consecutive_losses,
        )

    def check_and_reset_periods(self) -> None:
        """Check if daily/hourly periods need reset."""
        now = datetime.utcnow()

        # Reset hourly
        if now - self.last_hourly_reset > timedelta(hours=1):
            self.hourly_pnl = Decimal("0")
            self.last_hourly_reset = now
            logger.info("hourly_pnl_reset")

        # Reset daily
        if now - self.last_daily_reset > timedelta(days=1):
            self.daily_pnl = Decimal("0")
            self.last_daily_reset = now
            logger.info("daily_pnl_reset")

    def get_win_rate(self) -> Decimal:
        """
        Calculate win rate (%).

        Returns:
            Win rate as percentage (0-100)
        """
        if not self.completed_trades:
            return Decimal("0")

        wins = sum(1 for t in self.completed_trades if t["is_profit"])
        return Decimal(wins) / len(self.completed_trades) * Decimal("100")

    def get_average_profit(self) -> Decimal:
        """
        Calculate average profit per trade.

        Returns:
            Average P&L per trade in USD
        """
        if not self.completed_trades:
            return Decimal("0")

        total = sum(t["pnl_usd"] for t in self.completed_trades)
        return total / len(self.completed_trades)

    def get_sharpe_ratio(self) -> Decimal:
        """
        Calculate simple Sharpe ratio.

        Returns:
            Sharpe ratio (higher is better)
        """
        if len(self.completed_trades) < 10:
            return Decimal("0")

        # Calculate average and std dev
        pnls = [t["pnl_usd"] for t in self.completed_trades]
        avg = sum(pnls) / len(pnls)

        variance = sum((pnl - avg) ** 2 for pnl in pnls) / len(pnls)
        std_dev = variance ** Decimal("0.5")

        if std_dev == 0:
            return Decimal("0")

        return avg / std_dev

    def get_total_wins(self) -> int:
        """
        Get total number of winning trades.

        Returns:
            Count of profitable trades
        """
        return sum(1 for t in self.completed_trades if t["is_profit"])

    def get_total_losses(self) -> int:
        """
        Get total number of losing trades.

        Returns:
            Count of losing trades
        """
        return sum(1 for t in self.completed_trades if not t["is_profit"])

    def get_largest_win(self) -> Decimal:
        """
        Get largest single win.

        Returns:
            Largest profit from a single trade
        """
        if not self.completed_trades:
            return Decimal("0")

        winning_trades = [t["pnl_usd"] for t in self.completed_trades if t["is_profit"]]
        return max(winning_trades) if winning_trades else Decimal("0")

    def get_largest_loss(self) -> Decimal:
        """
        Get largest single loss.

        Returns:
            Largest loss from a single trade
        """
        if not self.completed_trades:
            return Decimal("0")

        losing_trades = [
            t["pnl_usd"] for t in self.completed_trades if not t["is_profit"]
        ]
        return min(losing_trades) if losing_trades else Decimal("0")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive P&L statistics.

        Returns:
            Dictionary with P&L metrics
        """
        return {
            "total_pnl_usd": float(self.total_pnl),
            "daily_pnl_usd": float(self.daily_pnl),
            "hourly_pnl_usd": float(self.hourly_pnl),
            "total_trades": len(self.completed_trades),
            "total_wins": self.get_total_wins(),
            "total_losses": self.get_total_losses(),
            "win_rate_percent": float(self.get_win_rate()),
            "average_profit_usd": float(self.get_average_profit()),
            "sharpe_ratio": float(self.get_sharpe_ratio()),
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "largest_win_usd": float(self.get_largest_win()),
            "largest_loss_usd": float(self.get_largest_loss()),
        }

    def reset_all(self) -> None:
        """Reset all P&L tracking (use with caution)."""
        self.daily_pnl = Decimal("0")
        self.hourly_pnl = Decimal("0")
        self.total_pnl = Decimal("0")
        self.completed_trades.clear()
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.last_daily_reset = datetime.utcnow()
        self.last_hourly_reset = datetime.utcnow()
        logger.warning("P&L tracker reset")
