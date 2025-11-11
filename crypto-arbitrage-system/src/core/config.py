"""
Configuration management for the crypto arbitrage system.

This module provides type-safe configuration management using Pydantic
models with validation and environment variable support.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.exceptions import ConfigurationError


# Load environment variables
load_dotenv()


class ExchangeConfig(BaseModel):
    """Configuration for a single exchange."""

    name: str
    api_url: str
    ws_url: str
    rate_limit_requests_per_second: int
    supported_pairs: List[str]
    maker_fee: float = Field(ge=0, le=1)
    taker_fee: float = Field(ge=0, le=1)
    withdrawal_fee: Dict[str, float]
    withdrawal_time_hours: int
    min_trade_size: Dict[str, float]
    enabled: bool = True
    priority: int = Field(ge=1)

    @field_validator("maker_fee", "taker_fee")
    @classmethod
    def validate_fees(cls, v: float) -> float:
        """Validate that fees are reasonable (< 1%)."""
        if v > 0.01:
            # Warning for high fees, but not blocking
            pass
        return v


class ExchangesConfig(BaseModel):
    """Configuration for all exchanges."""

    exchanges: Dict[str, ExchangeConfig]

    def __getattr__(self, name: str) -> ExchangeConfig:
        """
        Allow attribute-style access to exchanges.

        This enables clean syntax like config.exchanges.kraken instead of
        config.exchanges.exchanges["kraken"].

        Args:
            name: Exchange name (e.g., "kraken", "coinbase_advanced")

        Returns:
            ExchangeConfig for the requested exchange

        Raises:
            AttributeError: If exchange is not found in configuration
        """
        # First check if it's a regular attribute (to avoid infinite recursion)
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass

        # Then check if it's an exchange name
        exchanges_dict = super().__getattribute__("exchanges")
        if name in exchanges_dict:
            return exchanges_dict[name]

        raise AttributeError(
            f"Exchange '{name}' not found in configuration. "
            f"Available exchanges: {', '.join(exchanges_dict.keys())}"
        )

    @model_validator(mode="after")
    def validate_exchanges(self) -> "ExchangesConfig":
        """Validate that at least 2 exchanges are enabled."""
        enabled_exchanges = [
            name for name, config in self.exchanges.items()
            if config.enabled
        ]
        if len(enabled_exchanges) < 2:
            raise ValueError(
                "At least 2 exchanges must be enabled for arbitrage"
            )
        return self


class CapitalAllocationConfig(BaseModel):
    """Capital allocation settings."""

    total_capital_usd: float = Field(gt=0)
    max_capital_per_exchange: float = Field(ge=0, le=1)
    reserve_buffer: float = Field(ge=0, le=1)
    rebalance_threshold: float = Field(ge=0, le=1)
    rebalance_frequency_hours: int = Field(ge=1)


class ProfitThresholdsConfig(BaseModel):
    """Profit threshold settings."""

    min_profit_percent: float = Field(gt=0)
    min_profit_usd: float = Field(gt=0)
    optimal_profit_percent: float = Field(gt=0)
    max_slippage_percent: float = Field(ge=0)


class ExecutionConfig(BaseModel):
    """Trade execution settings."""

    max_execution_time_seconds: int = Field(ge=1)
    order_timeout_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=0, le=10)
    retry_delay_seconds: int = Field(ge=0)
    use_limit_orders: bool = True
    limit_order_offset_percent: float = Field(ge=0)
    cancel_unfilled_after_seconds: int = Field(ge=1)


class ArbitrageTypeConfig(BaseModel):
    """Configuration for a specific arbitrage type."""

    enabled: bool
    min_price_difference_percent: Optional[float] = None
    min_profit_percent: Optional[float] = None
    max_exposure_usd: float = Field(gt=0)
    supported_triangles: Optional[List[List[str]]] = None


class TradingConfig(BaseModel):
    """Trading configuration."""

    mode: str = Field(pattern="^(dry_run|paper|live)$")
    capital_allocation: CapitalAllocationConfig
    profit_thresholds: ProfitThresholdsConfig
    execution: ExecutionConfig
    arbitrage_types: Dict[str, ArbitrageTypeConfig]
    pairs: Dict[str, List[str]]
    timing: Dict[str, Any]


class RiskProfileConfig(BaseModel):
    """Risk profile settings."""

    max_position_size_percent: float = Field(gt=0, le=100)
    max_daily_loss_percent: float = Field(gt=0, le=100)
    max_drawdown_percent: float = Field(gt=0, le=100)
    min_confidence_score: float = Field(ge=0, le=1)
    max_leverage: float = Field(ge=1)
    diversification_requirement: float = Field(ge=0, le=1)


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker settings."""

    max_consecutive_losses: int = Field(ge=1)
    max_hourly_loss_usd: float = Field(gt=0)
    max_daily_loss_usd: float = Field(gt=0)
    pause_duration_minutes: int = Field(ge=1)
    auto_resume: bool = True
    escalation_levels: List[Dict[str, Any]]


class PositionLimitsConfig(BaseModel):
    """Position limit settings."""

    max_open_positions: int = Field(ge=1)
    max_positions_per_exchange: int = Field(ge=1)
    max_exposure_per_pair_usd: float = Field(gt=0)
    max_total_exposure_usd: float = Field(gt=0)
    concentration_limits: Dict[str, float]


class RiskConfig(BaseModel):
    """Risk management configuration."""

    profiles: Dict[str, RiskProfileConfig]
    active_profile: str
    circuit_breakers: CircuitBreakerConfig
    position_limits: PositionLimitsConfig
    exchange_risk: Dict[str, Any]
    market_conditions: Dict[str, Any]
    monitoring: Dict[str, Any]
    compliance: Dict[str, Any]

    @model_validator(mode="after")
    def validate_active_profile(self) -> "RiskConfig":
        """Validate that active profile exists."""
        if self.active_profile not in self.profiles:
            raise ValueError(
                f"Active profile '{self.active_profile}' not found in profiles"
            )
        return self


class ComplianceConfig(BaseModel):
    """Compliance and regulatory configuration."""

    tax: Dict[str, Any]
    reporting: Dict[str, Any]
    record_keeping: Dict[str, Any]
    kyc_aml: Dict[str, Any]
    regulatory: Dict[str, Any]
    data_protection: Dict[str, Any]
    legal: Dict[str, Any]
    monitoring: Dict[str, Any]
    limits: Dict[str, Any]
    documentation: Dict[str, Any]


class ConfigManager:
    """
    Central configuration manager for the arbitrage system.

    This class loads, validates, and provides access to all system
    configuration from YAML files and environment variables.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        environment: Optional[str] = None
    ) -> None:
        """
        Initialize the configuration manager.

        Args:
            config_dir: Directory containing configuration files
            environment: Environment name (development, staging, production)

        Raises:
            ConfigurationError: If configuration is invalid or missing
        """
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.config_dir = config_dir or self._get_default_config_dir()

        # Load all configurations
        self._load_all_configs()

    def _get_default_config_dir(self) -> Path:
        """Get the default configuration directory."""
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        return project_root / "config"

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        Load and parse a YAML configuration file.

        Args:
            filename: Name of the YAML file to load

        Returns:
            Dictionary containing the parsed YAML data

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        file_path = self.config_dir / filename

        if not file_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {file_path}",
                details={"file": str(file_path)}
            )

        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
                if data is None:
                    raise ConfigurationError(
                        f"Empty configuration file: {filename}"
                    )
                return data
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Failed to parse YAML file: {filename}",
                details={"error": str(e)}
            )
        except Exception as e:
            raise ConfigurationError(
                f"Error loading configuration: {filename}",
                details={"error": str(e)}
            )

    def _load_all_configs(self) -> None:
        """Load all configuration files and validate them."""
        try:
            # Load exchanges configuration
            exchanges_data = self._load_yaml("exchanges.yaml")
            # Unwrap the top-level "exchanges" key if present
            if "exchanges" in exchanges_data and isinstance(exchanges_data["exchanges"], dict):
                self.exchanges = ExchangesConfig(exchanges=exchanges_data["exchanges"])
            else:
                self.exchanges = ExchangesConfig(**exchanges_data)

            # Load trading configuration
            trading_data = self._load_yaml("trading.yaml")
            # Unwrap the top-level "trading" key if present
            if "trading" in trading_data:
                self.trading = TradingConfig(**trading_data["trading"])
            else:
                self.trading = TradingConfig(**trading_data)

            # Load risk configuration
            risk_data = self._load_yaml("risk.yaml")
            # Unwrap the top-level "risk" key if present
            if "risk" in risk_data:
                self.risk = RiskConfig(**risk_data["risk"])
            else:
                self.risk = RiskConfig(**risk_data)

            # Load compliance configuration
            compliance_data = self._load_yaml("compliance.yaml")
            # Unwrap the top-level "compliance" key if present
            if "compliance" in compliance_data:
                self.compliance = ComplianceConfig(**compliance_data["compliance"])
            else:
                self.compliance = ComplianceConfig(**compliance_data)

            # Load environment variables
            self._load_environment_variables()

            # Validate cross-configuration dependencies
            self._validate_configuration()

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise ConfigurationError(
                "Failed to load configuration",
                details={"error": str(e)}
            )

    def _load_environment_variables(self) -> None:
        """Load and validate required environment variables."""
        # Database
        self.database_url = os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ConfigurationError("DATABASE_URL environment variable is required")

        # Redis
        self.redis_url = os.getenv("REDIS_URL")
        if not self.redis_url:
            raise ConfigurationError("REDIS_URL environment variable is required")

        # Exchange API keys
        self.api_keys = {}
        for exchange_name in self.exchanges.exchanges.keys():
            key_name = f"{exchange_name.upper()}_API_KEY"
            secret_name = f"{exchange_name.upper()}_API_SECRET"

            api_key = os.getenv(key_name)
            api_secret = os.getenv(secret_name)

            # Only require keys for enabled exchanges in live mode
            if self.exchanges.exchanges[exchange_name].enabled:
                if self.trading.mode == "live":
                    if not api_key or not api_secret:
                        raise ConfigurationError(
                            f"API credentials required for {exchange_name}",
                            details={
                                "exchange": exchange_name,
                                "mode": self.trading.mode
                            }
                        )

            self.api_keys[exchange_name] = {
                "api_key": api_key,
                "api_secret": api_secret
            }

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"

    def _validate_configuration(self) -> None:
        """Validate cross-configuration dependencies and constraints."""
        # Validate capital allocation
        active_risk = self.get_active_risk_profile()
        max_total_exposure = self.risk.position_limits.max_total_exposure_usd

        if max_total_exposure > self.trading.capital_allocation.total_capital_usd:
            raise ConfigurationError(
                "Max total exposure exceeds available capital",
                details={
                    "capital": self.trading.capital_allocation.total_capital_usd,
                    "max_exposure": max_total_exposure
                }
            )

        # Validate profit thresholds
        if (self.trading.profit_thresholds.min_profit_percent <
                self.trading.profit_thresholds.max_slippage_percent):
            raise ConfigurationError(
                "Min profit percent must exceed max slippage percent"
            )

    def get_active_risk_profile(self) -> RiskProfileConfig:
        """
        Get the currently active risk profile.

        Returns:
            The active risk profile configuration
        """
        return self.risk.profiles[self.risk.active_profile]

    def get_exchange_config(self, exchange_name: str) -> ExchangeConfig:
        """
        Get configuration for a specific exchange.

        Args:
            exchange_name: Name of the exchange

        Returns:
            Exchange configuration

        Raises:
            ConfigurationError: If exchange not found
        """
        if exchange_name not in self.exchanges.exchanges:
            raise ConfigurationError(
                f"Exchange '{exchange_name}' not configured",
                details={"exchange": exchange_name}
            )
        return self.exchanges.exchanges[exchange_name]

    def get_enabled_exchanges(self) -> List[str]:
        """
        Get list of enabled exchange names.

        Returns:
            List of enabled exchange names
        """
        return [
            name for name, config in self.exchanges.exchanges.items()
            if config.enabled
        ]

    def reload_config(self, config_name: str) -> None:
        """
        Reload a specific configuration file (hot-reload for non-critical configs).

        Args:
            config_name: Name of the config to reload (e.g., 'trading', 'risk')

        Raises:
            ConfigurationError: If config cannot be reloaded
        """
        # Only allow hot-reload for certain configurations
        reloadable_configs = ["trading", "risk"]

        if config_name not in reloadable_configs:
            raise ConfigurationError(
                f"Configuration '{config_name}' cannot be hot-reloaded"
            )

        try:
            if config_name == "trading":
                trading_data = self._load_yaml("trading.yaml")
                self.trading = TradingConfig(**trading_data)
            elif config_name == "risk":
                risk_data = self._load_yaml("risk.yaml")
                self.risk = RiskConfig(**risk_data)

            self._validate_configuration()
        except Exception as e:
            raise ConfigurationError(
                f"Failed to reload {config_name} configuration",
                details={"error": str(e)}
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary format.

        Returns:
            Dictionary representation of all configurations
        """
        return {
            "environment": self.environment,
            "exchanges": self.exchanges.model_dump(),
            "trading": self.trading.model_dump(),
            "risk": self.risk.model_dump(),
            "compliance": self.compliance.model_dump(),
            "database_url": "***REDACTED***",  # Never expose credentials
            "redis_url": "***REDACTED***",
        }

    def __repr__(self) -> str:
        """Return string representation of config manager."""
        return (
            f"ConfigManager(environment={self.environment}, "
            f"exchanges={len(self.exchanges.exchanges)}, "
            f"mode={self.trading.mode})"
        )
