"""
Tests for execution engine.

Tests:
- Execution plan creation
- Risk validation integration
- Balance reservation/release
- Dry-run execution
- Error handling
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.execution.engine import ExecutionEngine
from src.execution.models import ExecutionState
from src.models.opportunity import ArbitrageOpportunity
from src.risk.models import ValidationResult, RiskLevel


class TestExecutionEngine:
    """Test execution engine functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock exchanges
        self.exchanges = {
            "Kraken": MagicMock(),
            "Coinbase Advanced": MagicMock(),
        }

        # Mock risk manager
        self.risk_manager = MagicMock()

        # Mock config
        self.config = MagicMock()

        # Create engine
        self.engine = ExecutionEngine(
            self.exchanges,
            self.risk_manager,
            self.config
        )

    def create_test_opportunity(self):
        """Create a test opportunity."""
        return ArbitrageOpportunity(
            strategy="cross_exchange",
            buy_exchange="Kraken",
            sell_exchange="Coinbase Advanced",
            symbol="BTC/USD",
            buy_price=Decimal("50000"),
            sell_price=Decimal("50250"),
            gross_profit_percent=Decimal("0.5"),
            gross_profit_usd=Decimal("250"),
            net_profit_percent=Decimal("0.4"),
            net_profit_usd=Decimal("200"),
            total_fees_percent=Decimal("0.1"),
            total_fees_usd=Decimal("50"),
            max_quantity=Decimal("0.1"),
            confidence_score=Decimal("0.85"),
            risk_score=Decimal("0.3"),
        )

    def test_engine_initialization(self):
        """Test engine initialization."""
        assert self.engine.exchanges == self.exchanges
        assert self.engine.risk_manager == self.risk_manager
        assert self.engine.order_manager is not None
        assert self.engine.balance_manager is not None
        assert self.engine.coordinator is not None

    def test_create_execution_plan(self):
        """Test execution plan creation."""
        opportunity = self.create_test_opportunity()
        plan = self.engine._create_execution_plan(opportunity, dry_run=True)

        assert plan.opportunity_id == opportunity.opportunity_id
        assert plan.strategy == "cross_exchange"
        assert len(plan.orders) == 2
        assert plan.orders[0].side == "buy"
        assert plan.orders[1].side == "sell"
        assert plan.dry_run is True

    @pytest.mark.asyncio
    async def test_execution_rejected_by_risk_manager(self):
        """Test execution rejected by risk validation."""
        opportunity = self.create_test_opportunity()

        # Mock risk validation failure
        self.risk_manager.validate_trade.return_value = ValidationResult(
            passed=False,
            reason="Insufficient balance",
            risk_level=RiskLevel.CRITICAL
        )

        result = await self.engine.execute_opportunity(opportunity, dry_run=True)

        assert not result.success
        assert result.state == ExecutionState.REJECTED
        assert "Insufficient balance" in result.error_message

    @pytest.mark.asyncio
    async def test_execution_approved(self):
        """Test execution passes validation."""
        opportunity = self.create_test_opportunity()

        # Mock risk validation success
        self.risk_manager.validate_trade.return_value = ValidationResult(
            passed=True
        )

        # Mock balance manager
        self.engine.balance_manager.reserve_balance = MagicMock(return_value=True)
        self.engine.balance_manager.available_balances = {
            "Kraken": {"USD": Decimal("10000")},
            "Coinbase Advanced": {"USD": Decimal("10000")}
        }

        # Mock coordinator execution
        with patch.object(self.engine.coordinator, 'execute_plan', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = False  # Execution failed

            result = await self.engine.execute_opportunity(opportunity, dry_run=True)

            # Should pass validation but fail execution
            assert not result.success

    def test_balance_reservation(self):
        """Test balance reservation."""
        opportunity = self.create_test_opportunity()
        plan = self.engine._create_execution_plan(opportunity, dry_run=True)

        # Mock balance manager
        self.engine.balance_manager.reserve_balance = MagicMock(return_value=True)

        success = self.engine._reserve_balances(plan)

        assert success
        assert self.engine.balance_manager.reserve_balance.called

    def test_balance_reservation_failure(self):
        """Test balance reservation failure."""
        opportunity = self.create_test_opportunity()
        plan = self.engine._create_execution_plan(opportunity, dry_run=True)

        # Mock insufficient balance
        self.engine.balance_manager.reserve_balance = MagicMock(return_value=False)

        success = self.engine._reserve_balances(plan)

        assert not success

    def test_get_execution_status(self):
        """Test getting execution status."""
        opportunity = self.create_test_opportunity()
        plan = self.engine._create_execution_plan(opportunity, dry_run=True)

        # Track execution
        self.engine.executions[plan.execution_id] = plan

        # Retrieve status
        status = self.engine.get_execution_status(plan.execution_id)

        assert status is not None
        assert status.execution_id == plan.execution_id

    def test_get_stats(self):
        """Test getting execution statistics."""
        stats = self.engine.get_stats()

        assert "total_executions" in stats
        assert "successful" in stats
        assert "failed" in stats
        assert "success_rate" in stats
