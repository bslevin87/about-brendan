"""
Tests for risk manager.

Tests:
- Full validation flow
- Trading state changes
- Kill switch
- Integration of all components
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from src.risk.manager import RiskManager
from src.risk.models import TradingState, RiskLevel
from src.models.opportunity import ArbitrageOpportunity


class TestRiskManager:
    """Test risk manager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create mock config
        self.config = MagicMock()
        self.config.risk.active_profile = "conservative"
        self.config.trading.capital_allocation.total_capital_usd = 10000
        self.config.trading.profit_thresholds.min_profit_percent = 0.30
        self.config.risk.circuit_breakers.max_consecutive_losses = 5
        self.config.risk.circuit_breakers.pause_duration_minutes = 5

        # Mock profile
        profile = MagicMock()
        profile.max_position_size_percent = 10
        profile.max_daily_loss_percent = 2
        profile.min_confidence_score = 0.80
        profile.get = lambda key, default: default
        self.config.risk.profiles = {"conservative": profile}

        self.manager = RiskManager(self.config)

    def create_opportunity(
        self,
        net_profit_percent=Decimal("0.5"),
        confidence=Decimal("0.85"),
        risk=Decimal("0.3"),
    ):
        """Helper to create test opportunity."""
        return ArbitrageOpportunity(
            strategy="cross_exchange",
            buy_exchange="Kraken",
            sell_exchange="Coinbase Advanced",
            symbol="BTC/USD",
            buy_price=Decimal("50000"),
            sell_price=Decimal("50250"),
            gross_profit_percent=Decimal("0.5"),
            gross_profit_usd=Decimal("25"),
            net_profit_percent=net_profit_percent,
            net_profit_usd=Decimal("20"),
            total_fees_percent=Decimal("0.1"),
            total_fees_usd=Decimal("5"),
            max_quantity=Decimal("0.01"),
            confidence_score=confidence,
            risk_score=risk,
        )

    def test_initialization(self):
        """Test manager initialization."""
        assert self.manager.trading_state == TradingState.ACTIVE
        assert not self.manager.emergency.is_kill_switch_active()

    def test_validate_trade_passes(self):
        """Test successful validation."""
        opportunity = self.create_opportunity()
        balances = {"Kraken": {"USD": Decimal("5000")}}

        result = self.manager.validate_trade(opportunity, balances)
        assert result.passed

    def test_validate_trade_low_confidence(self):
        """Test validation fails on low confidence."""
        opportunity = self.create_opportunity(confidence=Decimal("0.5"))
        balances = {"Kraken": {"USD": Decimal("5000")}}

        result = self.manager.validate_trade(opportunity, balances)
        assert not result.passed
        assert "Confidence too low" in result.reason

    def test_validate_trade_high_risk(self):
        """Test validation fails on high risk."""
        opportunity = self.create_opportunity(risk=Decimal("0.8"))
        balances = {"Kraken": {"USD": Decimal("5000")}}

        result = self.manager.validate_trade(opportunity, balances)
        assert not result.passed
        assert "Risk too high" in result.reason

    def test_validate_trade_low_profit(self):
        """Test validation fails on low profit."""
        opportunity = self.create_opportunity(net_profit_percent=Decimal("0.1"))
        balances = {"Kraken": {"USD": Decimal("5000")}}

        result = self.manager.validate_trade(opportunity, balances)
        assert not result.passed
        assert "Profit too low" in result.reason

    def test_validate_trade_insufficient_balance(self):
        """Test validation fails on insufficient balance."""
        opportunity = self.create_opportunity()
        balances = {"Kraken": {"USD": Decimal("100")}}  # Not enough

        result = self.manager.validate_trade(opportunity, balances)
        assert not result.passed
        assert "Insufficient balance" in result.reason

    def test_validate_trade_kill_switch_active(self):
        """Test validation fails when kill switch active."""
        self.manager.activate_kill_switch("Manual test")

        opportunity = self.create_opportunity()
        balances = {"Kraken": {"USD": Decimal("5000")}}

        result = self.manager.validate_trade(opportunity, balances)
        assert not result.passed
        assert "Kill switch is active" in result.reason
        assert result.risk_level == RiskLevel.CRITICAL

    def test_open_and_close_position(self):
        """Test position lifecycle."""
        # Open position
        self.manager.open_position(
            position_id="pos1",
            exchange="Kraken",
            symbol="BTC/USD",
            side="long",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
        )

        assert self.manager.position_tracker.get_total_position_count() == 1

        # Record trade outcome
        self.manager.record_trade_outcome(
            position_id="pos1", pnl_usd=Decimal("100")
        )

        assert self.manager.position_tracker.get_total_position_count() == 0
        assert self.manager.pnl_tracker.total_pnl == Decimal("100")

    def test_trading_state_halted_on_daily_loss(self):
        """Test trading halts on daily loss limit."""
        # Record large losses
        for _ in range(3):
            self.manager.pnl_tracker.record_trade(Decimal("-100"))

        # Manually trigger state check
        self.manager._check_and_update_state()

        # Should be halted or restricted
        assert self.manager.trading_state in [
            TradingState.HALTED,
            TradingState.RESTRICTED,
            TradingState.CAUTIOUS,
        ]

    def test_activate_and_deactivate_kill_switch(self):
        """Test kill switch activation and deactivation."""
        assert not self.manager.emergency.is_kill_switch_active()

        self.manager.activate_kill_switch("Test activation")
        assert self.manager.emergency.is_kill_switch_active()
        assert self.manager.trading_state == TradingState.EMERGENCY

        self.manager.deactivate_kill_switch()
        assert not self.manager.emergency.is_kill_switch_active()
        assert self.manager.trading_state == TradingState.ACTIVE

    def test_get_status(self):
        """Test comprehensive status retrieval."""
        status = self.manager.get_status()

        assert "trading_state" in status
        assert "circuit_breaker" in status
        assert "kill_switch" in status
        assert "positions" in status
        assert "pnl" in status
        assert "limits" in status

    def test_reset_circuit_breaker(self):
        """Test circuit breaker manual reset."""
        # Trigger circuit breaker
        for _ in range(5):
            self.manager.circuit_breaker.record_failure()

        assert not self.manager.circuit_breaker.is_trading_allowed()

        # Reset
        self.manager.reset_circuit_breaker()
        assert self.manager.circuit_breaker.is_trading_allowed()
