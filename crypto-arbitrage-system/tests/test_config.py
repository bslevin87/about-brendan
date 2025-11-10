"""
Tests for configuration management.

This module tests configuration loading, validation, and error handling.
"""
import pytest

from src.core.config import ConfigManager
from src.core.exceptions import ConfigurationError


class TestConfigManager:
    """Test configuration manager functionality."""

    def test_config_loading(self, config: ConfigManager) -> None:
        """Test that configuration loads successfully."""
        assert config is not None
        assert config.exchanges is not None
        assert config.trading is not None
        assert config.risk is not None
        assert config.compliance is not None

    def test_enabled_exchanges(self, config: ConfigManager) -> None:
        """Test getting enabled exchanges."""
        enabled = config.get_enabled_exchanges()
        assert len(enabled) >= 2
        assert "test_exchange" in enabled
        assert "test_exchange_2" in enabled

    def test_exchange_config(self, config: ConfigManager) -> None:
        """Test getting specific exchange configuration."""
        exchange_config = config.get_exchange_config("test_exchange")
        assert exchange_config.name == "Test Exchange"
        assert exchange_config.maker_fee == 0.001
        assert exchange_config.taker_fee == 0.002
        assert "BTC/USD" in exchange_config.supported_pairs

    def test_invalid_exchange_config(self, config: ConfigManager) -> None:
        """Test error handling for invalid exchange."""
        with pytest.raises(ConfigurationError):
            config.get_exchange_config("nonexistent_exchange")

    def test_risk_profile(self, config: ConfigManager) -> None:
        """Test getting active risk profile."""
        profile = config.get_active_risk_profile()
        assert profile is not None
        assert profile.max_position_size_percent > 0
        assert profile.min_confidence_score > 0

    def test_trading_mode(self, config: ConfigManager) -> None:
        """Test trading mode configuration."""
        assert config.trading.mode in ["dry_run", "paper", "live"]

    def test_capital_allocation(self, config: ConfigManager) -> None:
        """Test capital allocation settings."""
        capital = config.trading.capital_allocation
        assert capital.total_capital_usd > 0
        assert 0 <= capital.max_capital_per_exchange <= 1
        assert 0 <= capital.reserve_buffer <= 1

    def test_profit_thresholds(self, config: ConfigManager) -> None:
        """Test profit threshold settings."""
        thresholds = config.trading.profit_thresholds
        assert thresholds.min_profit_percent > 0
        assert thresholds.min_profit_usd > 0

    def test_circuit_breakers(self, config: ConfigManager) -> None:
        """Test circuit breaker settings."""
        breakers = config.risk.circuit_breakers
        assert breakers.max_consecutive_losses > 0
        assert breakers.max_hourly_loss_usd > 0
        assert breakers.max_daily_loss_usd > 0

    def test_position_limits(self, config: ConfigManager) -> None:
        """Test position limit settings."""
        limits = config.risk.position_limits
        assert limits.max_open_positions > 0
        assert limits.max_positions_per_exchange > 0

    def test_config_to_dict(self, config: ConfigManager) -> None:
        """Test configuration serialization."""
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert "environment" in config_dict
        assert "exchanges" in config_dict
        assert "trading" in config_dict
        assert "risk" in config_dict
        # Credentials should be redacted
        assert config_dict["database_url"] == "***REDACTED***"

    def test_config_repr(self, config: ConfigManager) -> None:
        """Test string representation of config."""
        repr_str = repr(config)
        assert "ConfigManager" in repr_str
        assert "test" in repr_str.lower()


class TestConfigValidation:
    """Test configuration validation logic."""

    def test_at_least_two_exchanges_required(
        self, test_config_dir, test_env_vars, monkeypatch
    ) -> None:
        """Test that at least 2 exchanges must be enabled."""
        import yaml
        from pathlib import Path

        # Modify config to have only 1 enabled exchange
        exchanges_file = test_config_dir / "exchanges.yaml"
        with open(exchanges_file, "r") as f:
            exchanges_data = yaml.safe_load(f)

        exchanges_data["exchanges"]["test_exchange_2"]["enabled"] = False

        with open(exchanges_file, "w") as f:
            yaml.dump(exchanges_data, f)

        # Should raise error when loading
        with pytest.raises(Exception):
            ConfigManager(config_dir=test_config_dir)

    def test_fee_validation(self, config: ConfigManager) -> None:
        """Test that fees are validated correctly."""
        exchange = config.get_exchange_config("test_exchange")
        assert 0 <= exchange.maker_fee <= 1
        assert 0 <= exchange.taker_fee <= 1

    def test_risk_profile_exists(self, config: ConfigManager) -> None:
        """Test that active risk profile exists in profiles."""
        assert config.risk.active_profile in config.risk.profiles


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_database_url_loaded(self, config: ConfigManager) -> None:
        """Test that DATABASE_URL is loaded."""
        assert config.database_url is not None
        assert len(config.database_url) > 0

    def test_redis_url_loaded(self, config: ConfigManager) -> None:
        """Test that REDIS_URL is loaded."""
        assert config.redis_url is not None
        assert len(config.redis_url) > 0

    def test_api_keys_loaded(self, config: ConfigManager) -> None:
        """Test that API keys are loaded for enabled exchanges."""
        assert "test_exchange" in config.api_keys
        assert config.api_keys["test_exchange"]["api_key"] is not None

    def test_log_level_loaded(self, config: ConfigManager) -> None:
        """Test that log level is loaded."""
        assert config.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
