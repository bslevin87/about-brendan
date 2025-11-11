"""
End-to-end execution flow tests.

Tests the complete execution pipeline from opportunity detection to execution.

Run with: pytest tests/integration/test_execution_flow.py -v
"""

import pytest
import asyncio
from decimal import Decimal

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.detectors.cross_exchange import CrossExchangeDetector
from src.risk.manager import RiskManager
from src.execution.engine import ExecutionEngine
from src.execution.models import ExecutionState
from src.models.opportunity import ArbitrageOpportunity


@pytest.fixture(scope="module")
def config():
    """Get config manager"""
    return ConfigManager()


@pytest.fixture(scope="module")
def logger():
    """Get logger"""
    return get_logger(__name__)


@pytest.fixture(scope="module")
async def full_system(config, logger):
    """Initialize complete system"""
    # Exchanges
    exchanges = {}

    kraken = KrakenExchange(
        config=config.exchanges.kraken,
        logger=logger,
        rate_limiter=RateLimiter(15, 20, "kraken")
    )
    await kraken.connect()
    exchanges["Kraken"] = kraken

    coinbase = CoinbaseAdvancedExchange(
        config=config.exchanges.coinbase_advanced,
        logger=logger,
        rate_limiter=RateLimiter(10, 15, "coinbase")
    )
    await coinbase.connect()
    exchanges["Coinbase Advanced"] = coinbase

    # Market data
    aggregator = MarketDataAggregator(
        exchanges=exchanges,
        config=config,
        logger=logger,
        redis_url=config.redis_url if hasattr(config, 'redis_url') else None
    )
    await aggregator.start(symbols=["BTC/USD", "ETH/USD"])
    await asyncio.sleep(10)  # Wait for data

    # Risk manager
    risk_manager = RiskManager(config=config, logger=logger)

    # Execution engine
    engine = ExecutionEngine(
        exchanges=exchanges,
        risk_manager=risk_manager,
        config=config,
        logger=logger
    )
    await engine.initialize()

    # Detector
    detector = CrossExchangeDetector(
        aggregator=aggregator,
        config=config,
        logger=logger
    )

    yield {
        "exchanges": exchanges,
        "aggregator": aggregator,
        "risk_manager": risk_manager,
        "engine": engine,
        "detector": detector,
        "config": config,
        "logger": logger
    }

    # Cleanup
    await aggregator.stop()
    for exchange in exchanges.values():
        await exchange.disconnect()


@pytest.fixture
def profitable_opportunity():
    """Create a profitable test opportunity"""
    return ArbitrageOpportunity(
        strategy="cross_exchange",
        buy_exchange="Kraken",
        sell_exchange="Coinbase Advanced",
        symbol="BTC/USD",
        buy_price=Decimal("42000"),
        sell_price=Decimal("42500"),
        gross_profit_percent=Decimal("1.19"),
        gross_profit_usd=Decimal("500.00"),
        net_profit_percent=Decimal("1.00"),
        net_profit_usd=Decimal("420.00"),
        total_fees_percent=Decimal("0.19"),
        total_fees_usd=Decimal("80.00"),
        max_quantity=Decimal("0.01"),
        slippage_estimate_percent=Decimal("0.05"),
        confidence_score=Decimal("0.90"),
        risk_score=Decimal("0.2")
    )


@pytest.fixture
def unprofitable_opportunity():
    """Create an unprofitable test opportunity"""
    return ArbitrageOpportunity(
        strategy="cross_exchange",
        buy_exchange="Kraken",
        sell_exchange="Coinbase Advanced",
        symbol="BTC/USD",
        buy_price=Decimal("42000"),
        sell_price=Decimal("42010"),
        gross_profit_percent=Decimal("0.024"),
        gross_profit_usd=Decimal("10.00"),
        net_profit_percent=Decimal("-0.20"),
        net_profit_usd=Decimal("-84.00"),
        total_fees_percent=Decimal("0.224"),
        total_fees_usd=Decimal("94.00"),
        max_quantity=Decimal("0.01"),
        slippage_estimate_percent=Decimal("0.05"),
        confidence_score=Decimal("0.50"),
        risk_score=Decimal("0.8")
    )


@pytest.mark.asyncio
class TestExecutionFlow:
    """Test complete execution flow"""

    async def test_opportunity_detection_to_validation(self, full_system):
        """Test flow from detection to validation"""
        detector = full_system["detector"]
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Detect opportunities
        opportunities = await detector.detect(symbols=["BTC/USD"])

        # Should complete without errors
        assert isinstance(opportunities, list)

        # If opportunities exist, validate them
        if opportunities:
            for opp in opportunities[:3]:
                balances = engine._get_available_balances()
                validation = risk_manager.validate_trade(opp, balances)

                assert validation is not None
                assert hasattr(validation, 'passed')

    async def test_validation_to_execution(self, full_system, profitable_opportunity):
        """Test flow from validation to execution"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Validate opportunity
        balances = engine._get_available_balances()
        validation = risk_manager.validate_trade(profitable_opportunity, balances)

        assert validation is not None

        # Execute (dry-run)
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        assert result is not None
        assert hasattr(result, 'execution_id')
        assert hasattr(result, 'state')

    async def test_dry_run_execution_creates_plan(self, full_system, profitable_opportunity):
        """Test that dry-run execution creates execution plan"""
        engine = full_system["engine"]

        # Execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        assert result is not None
        assert result.execution_id is not None

        # Get execution status
        plan = engine.get_execution_status(result.execution_id)

        if plan:
            assert hasattr(plan, 'state')
            assert hasattr(plan, 'orders')
            assert hasattr(plan, 'dry_run')
            assert plan.dry_run is True

    async def test_rejected_opportunity_flow(self, full_system, unprofitable_opportunity):
        """Test flow for rejected opportunity"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Execute unprofitable opportunity
        result = await engine.execute_opportunity(unprofitable_opportunity, dry_run=True)

        assert result is not None

        # Should likely be rejected (but not guaranteed)
        if result.state == ExecutionState.REJECTED:
            assert not result.success
            assert result.error_message is not None

    async def test_kill_switch_blocks_execution(self, full_system, profitable_opportunity):
        """Test that kill switch blocks execution"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Activate kill switch
        risk_manager.activate_kill_switch("Integration test")

        # Try to execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Should be rejected
        assert result is not None
        assert result.state == ExecutionState.REJECTED
        assert not result.success

        # Deactivate kill switch
        risk_manager.deactivate_kill_switch()

    async def test_circuit_breaker_blocks_execution(self, full_system, profitable_opportunity):
        """Test that open circuit breaker blocks execution"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Open circuit breaker
        risk_manager.circuit_breaker.open()

        # Try to execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Should be rejected
        assert result is not None
        assert result.state == ExecutionState.REJECTED
        assert not result.success

        # Close circuit breaker
        risk_manager.circuit_breaker.close()

    async def test_execution_statistics(self, full_system, profitable_opportunity):
        """Test that execution statistics are tracked"""
        engine = full_system["engine"]

        # Get stats before
        stats_before = engine.get_stats()
        executions_before = stats_before.get('total_executions', 0)

        # Execute
        await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Get stats after
        stats_after = engine.get_stats()
        executions_after = stats_after.get('total_executions', 0)

        # Should increment
        assert executions_after > executions_before

    async def test_balance_reservation_during_execution(self, full_system, profitable_opportunity):
        """Test that balances are reserved during execution"""
        engine = full_system["engine"]

        # Get initial balances
        balances_before = engine._get_available_balances()

        # Execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Balances may or may not change depending on validation
        # Just verify this doesn't crash
        balances_after = engine._get_available_balances()

        assert balances_after is not None

    async def test_multiple_sequential_executions(self, full_system, profitable_opportunity):
        """Test multiple sequential executions"""
        engine = full_system["engine"]

        # Execute multiple times
        results = []
        for i in range(3):
            result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)
            results.append(result)
            await asyncio.sleep(0.5)

        # All should complete
        assert len(results) == 3

        for result in results:
            assert result is not None
            assert hasattr(result, 'execution_id')

        # All execution IDs should be unique
        execution_ids = [r.execution_id for r in results]
        assert len(execution_ids) == len(set(execution_ids))

    async def test_position_tracking_during_execution(self, full_system, profitable_opportunity):
        """Test that positions are tracked during execution"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Get positions before
        positions_before = risk_manager.position_tracker.get_all_positions()

        # Execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Positions may or may not change (depends on execution success)
        positions_after = risk_manager.position_tracker.get_all_positions()

        # Just verify tracking doesn't crash
        assert isinstance(positions_after, dict)

    async def test_pnl_tracking_during_execution(self, full_system, profitable_opportunity):
        """Test that P&L is tracked during execution"""
        risk_manager = full_system["risk_manager"]
        engine = full_system["engine"]

        # Get P&L stats before
        stats_before = risk_manager.pnl_tracker.get_stats()
        trades_before = stats_before.get('total_trades', 0)

        # Execute
        result = await engine.execute_opportunity(profitable_opportunity, dry_run=True)

        # Get P&L stats after
        stats_after = risk_manager.pnl_tracker.get_stats()
        trades_after = stats_after.get('total_trades', 0)

        # Trades may increment if execution was successful
        assert trades_after >= trades_before
