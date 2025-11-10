"""
Risk management models.

Defines core data structures for risk management:
- Risk levels and trading states
- Validation results
- Risk limits
- Position tracking
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(Enum):
    """Risk level severity for validation failures."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TradingState(Enum):
    """Overall trading system state."""

    ACTIVE = "active"  # Normal operation
    CAUTIOUS = "cautious"  # Elevated risk, reduce position sizes
    RESTRICTED = "restricted"  # Only close positions, no new trades
    HALTED = "halted"  # All trading stopped
    EMERGENCY = "emergency"  # Emergency shutdown, close all positions


class ValidationResult:
    """
    Result of a validation check.

    Provides details on whether a check passed and why.
    Can be used as a boolean in conditions.
    """

    def __init__(
        self,
        passed: bool,
        reason: Optional[str] = None,
        risk_level: RiskLevel = RiskLevel.LOW,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize validation result.

        Args:
            passed: Whether validation passed
            reason: Human-readable reason for failure
            risk_level: Severity of the validation failure
            details: Additional context details
        """
        self.passed = passed
        self.reason = reason
        self.risk_level = risk_level
        self.details = details or {}
        self.timestamp = datetime.utcnow()

    def __bool__(self) -> bool:
        """Allow using ValidationResult as boolean."""
        return self.passed

    def __repr__(self) -> str:
        """String representation."""
        if self.passed:
            return f"ValidationResult(passed=True)"
        return f"ValidationResult(passed=False, reason='{self.reason}', risk={self.risk_level.value})"


@dataclass
class RiskLimits:
    """
    Risk limits configuration.

    Defines all thresholds and limits for trading operations.
    Typically loaded from config risk profile.
    """

    # Position limits
    max_position_size_percent: Decimal  # % of total capital per position
    max_positions_per_exchange: int
    max_total_open_positions: int
    max_exposure_per_pair_usd: Decimal
    max_total_exposure_usd: Decimal

    # Loss limits
    max_daily_loss_usd: Decimal
    max_hourly_loss_usd: Decimal
    max_consecutive_losses: int
    max_loss_per_trade_usd: Decimal

    # Performance thresholds
    min_confidence_score: Decimal  # 0-1 scale
    max_risk_score: Decimal  # 0-1 scale
    min_profit_threshold_percent: Decimal

    # Circuit breaker thresholds
    max_error_rate_percent: Decimal  # % of failed trades
    max_api_failures_per_minute: int
    pause_duration_minutes: int

    @classmethod
    def from_profile(cls, profile_name: str, config) -> "RiskLimits":
        """
        Create RiskLimits from config profile.

        Args:
            profile_name: Name of risk profile (conservative/moderate/aggressive)
            config: ConfigManager instance

        Returns:
            RiskLimits instance configured from profile
        """
        profile = config.risk.profiles[profile_name]
        total_capital = Decimal(
            str(config.trading.capital_allocation.total_capital_usd)
        )

        return cls(
            # Position limits
            max_position_size_percent=Decimal(
                str(profile.max_position_size_percent)
            ),
            max_positions_per_exchange=profile.get("max_positions_per_exchange", 3),
            max_total_open_positions=profile.get("max_open_positions", 10),
            max_exposure_per_pair_usd=Decimal(
                str(profile.get("max_exposure_per_pair_usd", 2000))
            ),
            max_total_exposure_usd=total_capital,
            # Loss limits
            max_daily_loss_usd=total_capital
            * Decimal(str(profile.max_daily_loss_percent))
            / Decimal("100"),
            max_hourly_loss_usd=total_capital
            * Decimal(str(profile.max_daily_loss_percent))
            / Decimal("400"),  # 1/4 of daily
            max_consecutive_losses=config.risk.circuit_breakers.max_consecutive_losses,
            max_loss_per_trade_usd=total_capital * Decimal("0.02"),  # 2% max per trade
            # Performance thresholds
            min_confidence_score=Decimal(str(profile.min_confidence_score)),
            max_risk_score=Decimal("0.7"),  # Max acceptable risk
            min_profit_threshold_percent=Decimal(
                str(config.trading.profit_thresholds.min_profit_percent)
            ),
            # Circuit breaker
            max_error_rate_percent=Decimal("20"),  # 20% error rate triggers breaker
            max_api_failures_per_minute=5,
            pause_duration_minutes=config.risk.circuit_breakers.pause_duration_minutes,
        )


@dataclass
class Position:
    """
    Open position tracking.

    Represents an active trading position with real-time P&L.
    """

    position_id: str
    exchange: str
    symbol: str
    side: str  # "long" or "short"
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl_usd: Decimal
    opened_at: datetime

    @property
    def exposure_usd(self) -> Decimal:
        """Calculate position exposure in USD."""
        return self.quantity * self.current_price

    @property
    def pnl_percent(self) -> Decimal:
        """Calculate P&L as percentage."""
        if self.entry_price == 0:
            return Decimal("0")

        if self.side == "long":
            return (
                (self.current_price - self.entry_price) / self.entry_price
            ) * Decimal("100")
        else:
            return (
                (self.entry_price - self.current_price) / self.entry_price
            ) * Decimal("100")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"Position(id={self.position_id[:8]}, {self.exchange}, {self.symbol}, "
            f"{self.side}, qty={self.quantity}, pnl={self.pnl_percent:.2f}%)"
        )
