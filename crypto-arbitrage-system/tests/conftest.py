"""
Pytest configuration and fixtures.

This module provides shared fixtures and configuration for all tests.
"""
import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import ConfigManager
from src.core.database import DatabaseManager
from src.models.base import Base


# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["LOG_TO_FILE"] = "false"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create an event loop for the test session.

    Yields:
        Event loop
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config_dir(tmp_path: Path) -> Path:
    """
    Create temporary config directory with test configurations.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to temporary config directory
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create minimal test configurations
    exchanges_config = """
exchanges:
  test_exchange:
    name: "Test Exchange"
    api_url: "https://api.test.com"
    ws_url: "wss://ws.test.com"
    rate_limit_requests_per_second: 10
    supported_pairs:
      - "BTC/USD"
      - "ETH/USD"
    maker_fee: 0.001
    taker_fee: 0.002
    withdrawal_fee:
      BTC: 0.0001
      ETH: 0.001
      USD: 1.0
    withdrawal_time_hours: 1
    min_trade_size:
      BTC: 0.0001
      ETH: 0.001
      USD: 10.0
    enabled: true
    priority: 1

  test_exchange_2:
    name: "Test Exchange 2"
    api_url: "https://api.test2.com"
    ws_url: "wss://ws.test2.com"
    rate_limit_requests_per_second: 10
    supported_pairs:
      - "BTC/USD"
      - "ETH/USD"
    maker_fee: 0.0015
    taker_fee: 0.0025
    withdrawal_fee:
      BTC: 0.0001
      ETH: 0.001
      USD: 1.0
    withdrawal_time_hours: 2
    min_trade_size:
      BTC: 0.0001
      ETH: 0.001
      USD: 10.0
    enabled: true
    priority: 2
"""

    trading_config = """
trading:
  mode: "dry_run"

  capital_allocation:
    total_capital_usd: 10000
    max_capital_per_exchange: 0.25
    reserve_buffer: 0.10
    rebalance_threshold: 0.15
    rebalance_frequency_hours: 24

  profit_thresholds:
    min_profit_percent: 0.30
    min_profit_usd: 5.00
    optimal_profit_percent: 0.50
    max_slippage_percent: 0.10

  execution:
    max_execution_time_seconds: 10
    order_timeout_seconds: 5
    max_retries: 3
    retry_delay_seconds: 1
    use_limit_orders: true
    limit_order_offset_percent: 0.05
    cancel_unfilled_after_seconds: 3

  arbitrage_types:
    cross_exchange:
      enabled: true
      min_price_difference_percent: 0.35
      max_exposure_usd: 5000

  pairs:
    primary:
      - "BTC/USD"
      - "ETH/USD"
    secondary: []
    cross: []

  timing:
    check_frequency_seconds: 1
    cooldown_between_trades_seconds: 5
    max_trades_per_minute: 10
    max_trades_per_hour: 100
    trading_hours:
      enabled: false
      start: "00:00"
      end: "23:59"
      timezone: "UTC"
"""

    risk_config = """
risk:
  profiles:
    conservative:
      max_position_size_percent: 10
      max_daily_loss_percent: 2
      max_drawdown_percent: 5
      min_confidence_score: 0.85
      max_leverage: 1.0
      diversification_requirement: 0.3

  active_profile: "conservative"

  circuit_breakers:
    max_consecutive_losses: 5
    max_hourly_loss_usd: 100
    max_daily_loss_usd: 500
    pause_duration_minutes: 30
    auto_resume: true
    escalation_levels:
      - threshold_usd: 100
        action: "pause_30min"

  position_limits:
    max_open_positions: 10
    max_positions_per_exchange: 3
    max_exposure_per_pair_usd: 2000
    max_total_exposure_usd: 9000
    concentration_limits:
      BTC: 0.40
      ETH: 0.30
      other: 0.30

  exchange_risk:
    max_balance_per_exchange_usd: 2500
    min_exchange_uptime_percent: 99.0
    max_withdrawal_delay_hours: 6
    exchange_health_check_interval_minutes: 5
    blacklist: []

  market_conditions:
    max_volatility_percent: 10
    min_liquidity_usd: 100000
    max_spread_percent: 1.0
    monitor_flash_crashes: true
    flash_crash_threshold_percent: 5

  monitoring:
    alert_on_breach: true
    auto_adjust_profile: false
    risk_report_frequency_hours: 6
    var_calculation_enabled: true
    var_confidence_level: 0.95
    var_time_horizon_days: 1

  compliance:
    max_transaction_size_usd: 10000
    kyc_required_above_usd: 5000
    suspicious_activity_threshold_usd: 7500
    geo_restrictions:
      blocked_countries: []
      allowed_countries: ["US"]
"""

    compliance_config = """
compliance:
  tax:
    cost_basis_method: "FIFO"
    tax_lot_tracking: true
    generate_8949: true
    tax_year: 2025
    jurisdiction: "US"
    state: "CA"
    wash_sale_tracking: true
    wash_sale_period_days: 30

  reporting:
    audit_trail: true
    trade_reconstruction: true
    retention_days: 2555
    export_formats:
      - "csv"
      - "json"
    generate_daily_reports: true
    generate_monthly_reports: true
    generate_annual_reports: true
    report_storage_path: "reports/"

  record_keeping:
    required_fields:
      - "timestamp"
      - "exchange"
      - "pair"
      - "side"
      - "quantity"
      - "price"
      - "fees"
    immutable_records: true
    backup_frequency_hours: 24
    backup_retention_days: 365

  kyc_aml:
    enabled: true
    max_transaction_size_usd: 10000
    alert_threshold_usd: 5000
    suspicious_activity_monitoring: true
    transaction_pattern_analysis: true
    velocity_checks:
      max_daily_volume_usd: 50000
      max_weekly_volume_usd: 200000
      max_monthly_volume_usd: 500000
    red_flags:
      - "rapid_fund_movement"
    reporting_requirements:
      ctr_threshold_usd: 10000
      sar_enabled: true
      fbar_threshold_usd: 10000

  regulatory:
    framework: "FinCEN"
    bsa_compliance: true
    aml_program: true
    cip_enabled: true
    exchanges_compliance:
      verify_exchange_registration: true
      required_licenses:
        - "MSB"
      check_sanctions_lists:
        - "OFAC"

  data_protection:
    encryption_at_rest: true
    encryption_in_transit: true
    pii_handling:
      enabled: false
      anonymization: true
      data_retention_days: 90
    gdpr_compliance: false
    ccpa_compliance: true

  legal:
    terms_accepted: false
    risk_disclosure: true
    disclaimer_required: true
    jurisdiction_acceptance: "US"
    legal_entity: "Individual"

  monitoring:
    real_time_compliance_check: true
    flag_suspicious_patterns: true
    auto_report_violations: false
    compliance_dashboard: true
    alert_recipients:
      - "compliance@example.com"

  limits:
    per_trade_usd: 10000
    per_day_usd: 50000
    per_month_usd: 500000
    lifetime_usd: 10000000

  documentation:
    maintain_sop: true
    incident_response_plan: true
    compliance_calendar: true
    training_required: false
    audit_frequency_months: 12
"""

    # Write config files
    (config_dir / "exchanges.yaml").write_text(exchanges_config)
    (config_dir / "trading.yaml").write_text(trading_config)
    (config_dir / "risk.yaml").write_text(risk_config)
    (config_dir / "compliance.yaml").write_text(compliance_config)

    return config_dir


@pytest.fixture
def test_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Set up test environment variables.

    Args:
        monkeypatch: Pytest monkeypatch fixture
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("TEST_EXCHANGE_API_KEY", "test_key")
    monkeypatch.setenv("TEST_EXCHANGE_API_SECRET", "test_secret")
    monkeypatch.setenv("TEST_EXCHANGE_2_API_KEY", "test_key_2")
    monkeypatch.setenv("TEST_EXCHANGE_2_API_SECRET", "test_secret_2")


@pytest.fixture
def config(test_config_dir: Path, test_env_vars: None) -> ConfigManager:
    """
    Create test configuration manager.

    Args:
        test_config_dir: Temporary config directory
        test_env_vars: Environment variables fixture

    Returns:
        ConfigManager instance
    """
    return ConfigManager(config_dir=test_config_dir)


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[DatabaseManager, None]:
    """
    Create test database manager with in-memory SQLite.

    Yields:
        DatabaseManager instance
    """
    # Use in-memory SQLite for testing
    db_url = "sqlite+aiosqlite:///:memory:"
    db_manager = DatabaseManager(db_url, echo=False)

    await db_manager.connect()
    await db_manager.create_all_tables()

    yield db_manager

    await db_manager.disconnect()


@pytest_asyncio.fixture
async def db_session(test_db: DatabaseManager) -> AsyncGenerator[AsyncSession, None]:
    """
    Create test database session.

    Args:
        test_db: Test database manager

    Yields:
        Database session
    """
    async with test_db.get_session() as session:
        yield session
