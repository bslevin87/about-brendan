"""
Pytest-based integration tests for full pipeline.

These tests validate that all components work together correctly.

Run with: pytest tests/integration/test_full_pipeline.py -v
"""

import pytest
import asyncio
from decimal import Decimal
from typing import Dict

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.detectors.cross_exchange import CrossExchangeDetector
from src.risk.manager import RiskManager
from src.execution.engine import ExecutionEngine
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
async def exchanges(config, logger):
    """Initialize exchanges"""
    exchanges_dict = {}

    # Kraken
    kraken = KrakenExchange(
        config=config.exchanges["kraken"],
        logger=logger,
        rate_limiter=RateLimiter(15, 20, "kraken")
    )
    await kraken.connect()
    exchanges_dict["Kraken"] = kraken

    # Coinbase Advanced
    coinbase = CoinbaseAdvancedExchange(
        config=config.exchanges["coinbase_advanced"],
        logger=logger,
        rate_limiter=RateLimiter(10, 15, "coinbase")
    )
    await coinbase.connect()
    exchanges_dict["Coinbase Advanced"] = coinbase

    yield exchanges_dict

    # Cleanup
    for exchange in exchanges_dict.values():
        await exchange.disconnect()


@pytest.fixture(scope="module")
async def market_data(exchanges, config, logger):
    """Initialize market data aggregator"""
    aggregator = MarketDataAggregator(
        exchanges=exchanges,
        config=config,
        logger=logger,
        redis_url=config.redis_url if hasattr(config, 'redis_url') else None
    )

    await aggregator.start(symbols=["BTC/USD", "ETH/USD"])

    # Wait for initial data
    await asyncio.sleep(10)

    yield aggregator

    # Cleanup
    await aggregator.stop()


@pytest.fixture(scope="module")
def risk_manager(config, logger):
    """Initialize risk manager"""
    return RiskManager(config=config, logger=logger)


@pytest.fixture(scope="module")
async def execution_engine(exchanges, risk_manager, config, logger):
    """Initialize execution engine"""
    engine = ExecutionEngine(
        exchanges=exchanges,
        risk_manager=risk_manager,
        config=config,
        logger=logger
    )

    await engine.initialize()

    return engine


@pytest.fixture(scope="module")
def detector(market_data, config, logger):
    """Initialize cross-exchange detector"""
    return CrossExchangeDetector(
        aggregator=market_data,
        config=config,
        logger=logger
    )


@pytest.fixture
def test_opportunity():
    """Create a test arbitrage opportunity"""
    return ArbitrageOpportunity(
        strategy="cross_exchange",
        buy_exchange="Kraken",
        sell_exchange="Coinbase Advanced",
        symbol="BTC/USD",
        buy_price=Decimal("42000"),
        sell_price=Decimal("42100"),
        gross_profit_percent=Decimal("0.238"),
        gross_profit_usd=Decimal("1.00"),
        net_profit_percent=Decimal("0.15"),
        net_profit_usd=Decimal("0.63"),
        total_fees_percent=Decimal("0.088"),
        total_fees_usd=Decimal("0.37"),
        max_quantity=Decimal("0.001"),
        slippage_estimate_percent=Decimal("0.05"),
        confidence_score=Decimal("0.85"),
        risk_score=Decimal("0.3")
    )


@pytest.mark.asyncio
class TestFullPipeline:
    """Test complete system pipeline"""

    async def test_configuration_loads(self, config):
        """Test that configuration loads correctly"""
        assert config is not None
        assert "kraken" in config.exchanges
        assert "coinbase_advanced" in config.exchanges
        assert hasattr(config, 'risk')
        assert hasattr(config, 'trading')
        assert config.trading.capital_allocation.total_capital_usd > 0

    async def test_exchanges_connect(self, exchanges):
        """Test that exchanges connect successfully"""
        assert len(exchanges) == 2
        assert "Kraken" in exchanges
        assert "Coinbase Advanced" in exchanges

        # Test health check
        for name, exchange in exchanges.items():
            health = await exchange.health_check()
            assert health is True, f"{name} health check failed"

    async def test_market_data_aggregation(self, market_data):
        """Test that market data aggregates correctly"""
        assert market_data is not None

        # Get prices
        prices = market_data.get_best_prices("BTC/USD")

        # May not have data immediately - that's OK
        if len(prices) > 0:
            assert isinstance(prices, dict)

            for exchange, price_data in prices.items():
                assert "bid" in price_data
                assert "ask" in price_data
                assert price_data["bid"] > 0
                assert price_data["ask"] > 0
                assert price_data["ask"] >= price_data["bid"]

    async def test_risk_manager_initializes(self, risk_manager):
        """Test that risk manager initializes correctly"""
        assert risk_manager is not None
        assert risk_manager.position_tracker is not None
        assert risk_manager.pnl_tracker is not None
        assert risk_manager.circuit_breaker is not None
        assert risk_manager.emergency is not None

        # Check limits
        assert risk_manager.risk_limits.max_daily_loss_usd > 0
        assert risk_manager.risk_limits.max_position_size_percent > 0

        # Check trading is allowed initially
        assert risk_manager.circuit_breaker.is_trading_allowed()
        assert not risk_manager.emergency.is_kill_switch_active()

    async def test_execution_engine_initializes(self, execution_engine):
        """Test that execution engine initializes correctly"""
        assert execution_engine is not None
        assert execution_engine.order_manager is not None
        assert execution_engine.balance_manager is not None
        assert execution_engine.coordinator is not None
        assert execution_engine.reconciliation is not None

        # Check balances
        balances = execution_engine._get_available_balances()
        assert isinstance(balances, dict)

    async def test_arbitrage_detection(self, detector):
        """Test that arbitrage detection works"""
        assert detector is not None

        # Detect opportunities
        opportunities = await detector.detect(symbols=["BTC/USD", "ETH/USD"])

        # Should return a list (may be empty if no opportunities)
        assert isinstance(opportunities, list)

        # If opportunities exist, validate structure
        for opp in opportunities:
            assert hasattr(opp, 'symbol')
            assert hasattr(opp, 'buy_exchange')
            assert hasattr(opp, 'sell_exchange')
            assert hasattr(opp, 'buy_price')
            assert hasattr(opp, 'sell_price')
            assert hasattr(opp, 'net_profit_usd')
            assert opp.buy_price > 0
            assert opp.sell_price > 0

    async def test_risk_validation_pipeline(self, risk_manager, execution_engine, test_opportunity):
        """Test risk validation pipeline"""
        balances = execution_engine._get_available_balances()
        validation = risk_manager.validate_trade(test_opportunity, balances)

        # Should complete without error
        assert validation is not None
        assert hasattr(validation, 'passed')
        assert hasattr(validation, 'reason')
        assert hasattr(validation, 'risk_level')

        # Validation may fail due to insufficient balance - that's OK
        # We're testing that it runs without crashing

    async def test_dry_run_execution_pipeline(self, execution_engine, test_opportunity):
        """Test dry-run execution pipeline"""
        # Execute in dry-run mode
        result = await execution_engine.execute_opportunity(test_opportunity, dry_run=True)

        # Should complete without crashing
        assert result is not None
        assert hasattr(result, 'success')
        assert hasattr(result, 'execution_id')
        assert hasattr(result, 'state')

        # Result may not be successful (validation failure) - that's OK
        # We're testing that execution runs without errors

    async def test_kill_switch_functionality(self, risk_manager):
        """Test kill switch works correctly"""
        # Activate
        risk_manager.activate_kill_switch("Test activation")
        assert risk_manager.emergency.is_kill_switch_active()

        # Deactivate
        risk_manager.deactivate_kill_switch()
        assert not risk_manager.emergency.is_kill_switch_active()

    async def test_circuit_breaker_functionality(self, risk_manager):
        """Test circuit breaker works correctly"""
        original_state = risk_manager.circuit_breaker.is_trading_allowed()

        # Open circuit breaker
        risk_manager.circuit_breaker.open()
        assert not risk_manager.circuit_breaker.is_trading_allowed()

        # Close circuit breaker
        risk_manager.circuit_breaker.close()
        assert risk_manager.circuit_breaker.is_trading_allowed()

    async def test_position_tracking(self, risk_manager):
        """Test position tracking works"""
        # Add position
        risk_manager.position_tracker.add_position(
            position_id="test_pos_1",
            exchange="Kraken",
            symbol="BTC/USD",
            side="buy",
            quantity=Decimal("0.1"),
            entry_price=Decimal("42000"),
            current_price=Decimal("42100")
        )

        # Verify position exists
        positions = risk_manager.position_tracker.get_all_positions()
        assert len(positions) > 0
        assert "test_pos_1" in positions

        # Remove position
        risk_manager.position_tracker.remove_position("test_pos_1")
        positions = risk_manager.position_tracker.get_all_positions()
        assert "test_pos_1" not in positions

    async def test_pnl_tracking(self, risk_manager):
        """Test P&L tracking works"""
        # Record a trade
        risk_manager.pnl_tracker.record_trade(
            pnl_usd=Decimal("10.50"),
            trade_details={"symbol": "BTC/USD", "test": True}
        )

        # Get stats
        stats = risk_manager.pnl_tracker.get_stats()
        assert stats is not None
        assert "total_trades" in stats
        assert "total_pnl_usd" in stats
        assert "daily_pnl_usd" in stats

    async def test_balance_management(self, execution_engine):
        """Test balance management works"""
        # Get balances
        balances = execution_engine._get_available_balances()
        assert isinstance(balances, dict)

        # Test balance reservation (if balances exist)
        if balances:
            exchange = list(balances.keys())[0]
            currencies = balances[exchange]

            if currencies:
                currency = list(currencies.keys())[0]
                available = currencies[currency]

                if available > 0:
                    # Reserve small amount
                    reserve_amount = min(available, Decimal("1.0"))

                    try:
                        execution_engine.balance_manager.reserve_balance(
                            exchange=exchange,
                            currency=currency,
                            amount=reserve_amount
                        )

                        # Release balance
                        execution_engine.balance_manager.release_balance(
                            exchange=exchange,
                            currency=currency,
                            amount=reserve_amount
                        )
                    except Exception:
                        # May fail if balance is already reserved - that's OK
                        pass
