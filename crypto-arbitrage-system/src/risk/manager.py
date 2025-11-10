"""
Central risk management system.

Coordinates all risk components:
- Pre-execution validation
- Position tracking
- P&L monitoring
- Circuit breakers
- Emergency controls
- Trading state management

PRINCIPLE: Capital preservation is paramount.
"""
from decimal import Decimal
from typing import Any, Dict, Optional

from src.core.logger import get_logger
from src.models.opportunity import ArbitrageOpportunity
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.emergency import EmergencyController
from src.risk.models import RiskLevel, RiskLimits, TradingState, ValidationResult
from src.risk.pnl_tracker import PnLTracker
from src.risk.position_tracker import PositionTracker
from src.risk.validators import PreExecutionValidator

logger = get_logger(__name__, component="risk_manager")


class RiskManager:
    """
    Central risk management system.

    Coordinates all risk components:
    - Pre-execution validation
    - Position tracking
    - P&L monitoring
    - Circuit breakers
    - Emergency controls
    """

    def __init__(self, config):
        """
        Initialize risk manager.

        Args:
            config: ConfigManager instance
        """
        self.config = config

        # Initialize risk limits from active profile
        active_profile = config.risk.active_profile
        self.risk_limits = RiskLimits.from_profile(active_profile, config)

        # Initialize components
        self.position_tracker = PositionTracker()
        self.pnl_tracker = PnLTracker()
        self.circuit_breaker = CircuitBreaker(config)
        self.emergency = EmergencyController()

        # Initialize validator
        self.validator = PreExecutionValidator(
            risk_limits=self.risk_limits,
            position_tracker=self.position_tracker,
            pnl_tracker=self.pnl_tracker,
        )

        # Trading state
        self.trading_state = TradingState.ACTIVE

        logger.info(
            "risk_manager_initialized",
            profile=active_profile,
            max_position_size_percent=str(self.risk_limits.max_position_size_percent),
            max_daily_loss_usd=str(self.risk_limits.max_daily_loss_usd),
            min_confidence_score=str(self.risk_limits.min_confidence_score),
        )

    def validate_trade(
        self,
        opportunity: ArbitrageOpportunity,
        available_balances: Dict[str, Dict[str, Decimal]],
    ) -> ValidationResult:
        """
        Main validation entry point.

        Args:
            opportunity: Arbitrage opportunity to validate
            available_balances: Available balances by exchange and currency

        Returns:
            ValidationResult indicating if trade should proceed
        """
        # Check kill switch first
        if self.emergency.is_kill_switch_active():
            return ValidationResult(
                passed=False,
                reason="Kill switch is active",
                risk_level=RiskLevel.CRITICAL,
            )

        # Check circuit breaker
        if not self.circuit_breaker.is_trading_allowed():
            return ValidationResult(
                passed=False,
                reason="Circuit breaker is open",
                risk_level=RiskLevel.CRITICAL,
            )

        # Check trading state
        if self.trading_state == TradingState.HALTED:
            return ValidationResult(
                passed=False,
                reason="Trading is halted",
                risk_level=RiskLevel.CRITICAL,
            )

        if self.trading_state == TradingState.RESTRICTED:
            return ValidationResult(
                passed=False,
                reason="Trading is restricted to closing positions only",
                risk_level=RiskLevel.HIGH,
            )

        # Run full validation
        result = self.validator.validate_all(opportunity, available_balances)

        # Record result in circuit breaker
        if result.passed:
            self.circuit_breaker.record_success()
        else:
            self.circuit_breaker.record_failure()

        return result

    def record_trade_outcome(
        self,
        position_id: str,
        pnl_usd: Decimal,
        trade_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record completed trade outcome.

        Args:
            position_id: Position identifier
            pnl_usd: Realized profit/loss in USD
            trade_details: Additional trade details
        """
        # Update P&L tracker
        self.pnl_tracker.record_trade(pnl_usd, trade_details)

        # Remove position
        self.position_tracker.remove_position(position_id)

        # Check if loss limits trigger state change
        self._check_and_update_state()

    def open_position(
        self,
        position_id: str,
        exchange: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
    ) -> None:
        """
        Record new position opened.

        Args:
            position_id: Position identifier
            exchange: Exchange name
            symbol: Trading pair
            side: Position side ("long" or "short")
            quantity: Position size
            entry_price: Entry price
        """
        self.position_tracker.add_position(
            position_id, exchange, symbol, side, quantity, entry_price
        )

    def update_position_prices(
        self, prices: Dict[str, Dict[str, Decimal]]
    ) -> None:
        """
        Update positions with current market prices.

        Args:
            prices: Dict of {symbol: {exchange: price}}
        """
        for position_id, position in self.position_tracker.positions.items():
            if position.symbol in prices:
                exchange_prices = prices[position.symbol]
                if position.exchange in exchange_prices:
                    current_price = exchange_prices[position.exchange]
                    self.position_tracker.update_position_price(
                        position_id, current_price
                    )

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive risk status.

        Returns:
            Dictionary with complete risk system status
        """
        return {
            "trading_state": self.trading_state.value,
            "circuit_breaker": self.circuit_breaker.get_status(),
            "kill_switch": self.emergency.get_kill_switch_status(),
            "positions": {
                "total_count": self.position_tracker.get_total_position_count(),
                "total_exposure_usd": float(
                    self.position_tracker.get_total_exposure()
                ),
                "unrealized_pnl_usd": float(
                    self.position_tracker.get_total_unrealized_pnl()
                ),
            },
            "pnl": self.pnl_tracker.get_stats(),
            "limits": {
                "max_daily_loss_usd": float(self.risk_limits.max_daily_loss_usd),
                "max_hourly_loss_usd": float(
                    self.risk_limits.max_hourly_loss_usd
                ),
                "max_positions": self.risk_limits.max_total_open_positions,
                "max_total_exposure_usd": float(
                    self.risk_limits.max_total_exposure_usd
                ),
                "min_confidence_score": float(
                    self.risk_limits.min_confidence_score
                ),
                "max_risk_score": float(self.risk_limits.max_risk_score),
            },
        }

    def _check_and_update_state(self) -> None:
        """Check conditions and update trading state if needed."""
        # Check if should halt
        if (
            self.pnl_tracker.daily_pnl
            < -self.risk_limits.max_daily_loss_usd
        ):
            self.set_trading_state(
                TradingState.HALTED, "Daily loss limit exceeded"
            )
        elif (
            self.pnl_tracker.consecutive_losses
            >= self.risk_limits.max_consecutive_losses
        ):
            self.set_trading_state(
                TradingState.RESTRICTED, "Too many consecutive losses"
            )
        elif (
            self.pnl_tracker.hourly_pnl
            < -self.risk_limits.max_hourly_loss_usd
        ):
            self.set_trading_state(
                TradingState.CAUTIOUS, "Hourly loss limit approached"
            )

    def set_trading_state(
        self, new_state: TradingState, reason: str
    ) -> None:
        """
        Manually set trading state.

        Args:
            new_state: New trading state
            reason: Reason for state change
        """
        if new_state == self.trading_state:
            return

        old_state = self.trading_state
        self.trading_state = new_state

        logger.warning(
            "trading_state_changed",
            old_state=old_state.value,
            new_state=new_state.value,
            reason=reason,
        )

    def activate_kill_switch(self, reason: str) -> None:
        """
        Activate emergency kill switch.

        Args:
            reason: Reason for activation
        """
        self.emergency.activate_kill_switch(reason)
        self.set_trading_state(TradingState.EMERGENCY, "Kill switch activated")

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch and resume normal operation."""
        self.emergency.deactivate_kill_switch()
        self.set_trading_state(TradingState.ACTIVE, "Kill switch deactivated")

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker."""
        self.circuit_breaker.reset()

    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get summary of recent validation decisions.

        Returns:
            Dictionary with validation statistics
        """
        return {
            "circuit_breaker": self.circuit_breaker.get_status(),
            "pnl": {
                "daily_pnl_usd": float(self.pnl_tracker.daily_pnl),
                "consecutive_losses": self.pnl_tracker.consecutive_losses,
            },
            "positions": {
                "total_count": self.position_tracker.get_total_position_count(),
                "total_exposure_usd": float(
                    self.position_tracker.get_total_exposure()
                ),
            },
        }
