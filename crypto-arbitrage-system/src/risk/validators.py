"""
Pre-execution validators.

Multi-layer validation before trade execution:
- Opportunity quality checks
- Position limit checks
- Loss limit checks
- Balance checks
- Exposure checks

PRINCIPLE: When in doubt, don't trade. Err on the side of caution.
"""
from decimal import Decimal
from typing import Any, Dict

from src.core.logger import get_logger
from src.models.opportunity import ArbitrageOpportunity
from src.risk.models import RiskLevel, RiskLimits, ValidationResult
from src.risk.pnl_tracker import PnLTracker
from src.risk.position_tracker import PositionTracker

logger = get_logger(__name__, component="validators")


class PreExecutionValidator:
    """
    Multi-layer validation before trade execution.

    Validates:
    - Sufficient balance
    - Position limits
    - Loss limits
    - Opportunity quality
    - Exchange health
    """

    def __init__(
        self,
        risk_limits: RiskLimits,
        position_tracker: PositionTracker,
        pnl_tracker: PnLTracker,
    ):
        """
        Initialize validator.

        Args:
            risk_limits: Risk limits configuration
            position_tracker: Position tracker instance
            pnl_tracker: P&L tracker instance
        """
        self.risk_limits = risk_limits
        self.position_tracker = position_tracker
        self.pnl_tracker = pnl_tracker

        logger.info("Pre-execution validator initialized")

    def validate_all(
        self, opportunity: ArbitrageOpportunity, available_balances: Dict[str, Dict[str, Decimal]]
    ) -> ValidationResult:
        """
        Run all validation checks.

        Args:
            opportunity: Arbitrage opportunity to validate
            available_balances: Dict of {exchange: {currency: balance}}

        Returns:
            ValidationResult indicating if trade should proceed
        """
        # Run all validators
        validators = [
            self.validate_opportunity_quality(opportunity),
            self.validate_position_limits(opportunity),
            self.validate_loss_limits(),
            self.validate_balance(opportunity, available_balances),
            self.validate_exposure(opportunity),
        ]

        # Check if all passed
        for result in validators:
            if not result.passed:
                logger.warning(
                    "validation_failed",
                    opportunity_id=opportunity.opportunity_id,
                    reason=result.reason,
                    risk_level=result.risk_level.value,
                    details=result.details,
                )
                return result

        # All validations passed
        logger.info(
            "all_validations_passed", opportunity_id=opportunity.opportunity_id
        )
        return ValidationResult(passed=True, reason="All checks passed")

    def validate_opportunity_quality(
        self, opportunity: ArbitrageOpportunity
    ) -> ValidationResult:
        """
        Validate opportunity meets quality thresholds.

        Args:
            opportunity: Opportunity to validate

        Returns:
            ValidationResult
        """
        # Check confidence score
        if opportunity.confidence_score < self.risk_limits.min_confidence_score:
            return ValidationResult(
                passed=False,
                reason=f"Confidence too low: {opportunity.confidence_score} < {self.risk_limits.min_confidence_score}",
                risk_level=RiskLevel.MEDIUM,
                details={"confidence": float(opportunity.confidence_score)},
            )

        # Check risk score
        if opportunity.risk_score > self.risk_limits.max_risk_score:
            return ValidationResult(
                passed=False,
                reason=f"Risk too high: {opportunity.risk_score} > {self.risk_limits.max_risk_score}",
                risk_level=RiskLevel.HIGH,
                details={"risk_score": float(opportunity.risk_score)},
            )

        # Check profit threshold
        if (
            opportunity.net_profit_percent
            < self.risk_limits.min_profit_threshold_percent
        ):
            return ValidationResult(
                passed=False,
                reason=f"Profit too low: {opportunity.net_profit_percent}% < {self.risk_limits.min_profit_threshold_percent}%",
                risk_level=RiskLevel.LOW,
                details={"profit_percent": float(opportunity.net_profit_percent)},
            )

        # Check if expired
        if opportunity.is_expired():
            return ValidationResult(
                passed=False,
                reason="Opportunity has expired",
                risk_level=RiskLevel.MEDIUM,
            )

        return ValidationResult(passed=True)

    def validate_position_limits(
        self, opportunity: ArbitrageOpportunity
    ) -> ValidationResult:
        """
        Validate position limits not exceeded.

        Args:
            opportunity: Opportunity to validate

        Returns:
            ValidationResult
        """
        # Check total position count
        total_positions = self.position_tracker.get_total_position_count()
        if total_positions >= self.risk_limits.max_total_open_positions:
            return ValidationResult(
                passed=False,
                reason=f"Max total positions reached: {total_positions}",
                risk_level=RiskLevel.HIGH,
                details={"current_positions": total_positions},
            )

        # Check per-exchange position count
        if opportunity.buy_exchange:
            buy_positions = self.position_tracker.get_position_count_by_exchange(
                opportunity.buy_exchange
            )
            if buy_positions >= self.risk_limits.max_positions_per_exchange:
                return ValidationResult(
                    passed=False,
                    reason=f"Max positions on {opportunity.buy_exchange}: {buy_positions}",
                    risk_level=RiskLevel.MEDIUM,
                )

        if opportunity.sell_exchange:
            sell_positions = self.position_tracker.get_position_count_by_exchange(
                opportunity.sell_exchange
            )
            if sell_positions >= self.risk_limits.max_positions_per_exchange:
                return ValidationResult(
                    passed=False,
                    reason=f"Max positions on {opportunity.sell_exchange}: {sell_positions}",
                    risk_level=RiskLevel.MEDIUM,
                )

        return ValidationResult(passed=True)

    def validate_loss_limits(self) -> ValidationResult:
        """
        Validate loss limits not exceeded.

        Returns:
            ValidationResult
        """
        # Reset periods if needed
        self.pnl_tracker.check_and_reset_periods()

        # Check daily loss
        if self.pnl_tracker.daily_pnl < -self.risk_limits.max_daily_loss_usd:
            return ValidationResult(
                passed=False,
                reason=f"Daily loss limit exceeded: ${abs(self.pnl_tracker.daily_pnl)}",
                risk_level=RiskLevel.CRITICAL,
                details={"daily_pnl": float(self.pnl_tracker.daily_pnl)},
            )

        # Check hourly loss
        if self.pnl_tracker.hourly_pnl < -self.risk_limits.max_hourly_loss_usd:
            return ValidationResult(
                passed=False,
                reason=f"Hourly loss limit exceeded: ${abs(self.pnl_tracker.hourly_pnl)}",
                risk_level=RiskLevel.HIGH,
                details={"hourly_pnl": float(self.pnl_tracker.hourly_pnl)},
            )

        # Check consecutive losses
        if (
            self.pnl_tracker.consecutive_losses
            >= self.risk_limits.max_consecutive_losses
        ):
            return ValidationResult(
                passed=False,
                reason=f"Too many consecutive losses: {self.pnl_tracker.consecutive_losses}",
                risk_level=RiskLevel.HIGH,
                details={"consecutive_losses": self.pnl_tracker.consecutive_losses},
            )

        return ValidationResult(passed=True)

    def validate_balance(
        self, opportunity: ArbitrageOpportunity, available_balances: Dict[str, Dict[str, Decimal]]
    ) -> ValidationResult:
        """
        Validate sufficient balance for trade.

        Args:
            opportunity: Opportunity to validate
            available_balances: Available balances by exchange and currency

        Returns:
            ValidationResult
        """
        # Calculate required capital
        position_size_usd = opportunity.max_quantity * opportunity.buy_price

        # Check if within position size limit
        max_position_usd = self.risk_limits.max_total_exposure_usd * (
            self.risk_limits.max_position_size_percent / Decimal("100")
        )
        if position_size_usd > max_position_usd:
            position_size_usd = max_position_usd  # Limit to max allowed

        # Extract currency from symbol (e.g., BTC/USD -> need USD on buy exchange)
        # Simplified - assumes USD for quote currency
        quote_currency = "USD"
        if opportunity.symbol and "/" in opportunity.symbol:
            quote_currency = opportunity.symbol.split("/")[1]

        # Check balance on buy exchange
        if opportunity.buy_exchange:
            buy_exchange_balances = available_balances.get(
                opportunity.buy_exchange, {}
            )
            buy_exchange_balance = buy_exchange_balances.get(
                quote_currency, Decimal("0")
            )

            if buy_exchange_balance < position_size_usd:
                return ValidationResult(
                    passed=False,
                    reason=f"Insufficient balance on {opportunity.buy_exchange}: ${buy_exchange_balance} < ${position_size_usd}",
                    risk_level=RiskLevel.CRITICAL,
                    details={
                        "required": float(position_size_usd),
                        "available": float(buy_exchange_balance),
                    },
                )

        return ValidationResult(passed=True)

    def validate_exposure(
        self, opportunity: ArbitrageOpportunity
    ) -> ValidationResult:
        """
        Validate exposure limits not exceeded.

        Args:
            opportunity: Opportunity to validate

        Returns:
            ValidationResult
        """
        # Calculate new exposure
        position_size_usd = opportunity.max_quantity * opportunity.buy_price

        # Check total exposure
        current_total_exposure = self.position_tracker.get_total_exposure()
        new_total_exposure = current_total_exposure + position_size_usd

        if new_total_exposure > self.risk_limits.max_total_exposure_usd:
            return ValidationResult(
                passed=False,
                reason=f"Total exposure limit exceeded: ${new_total_exposure} > ${self.risk_limits.max_total_exposure_usd}",
                risk_level=RiskLevel.HIGH,
                details={
                    "current_exposure": float(current_total_exposure),
                    "new_exposure": float(new_total_exposure),
                },
            )

        # Check per-symbol exposure
        if opportunity.symbol:
            current_symbol_exposure = self.position_tracker.get_exposure_by_symbol(
                opportunity.symbol
            )
            new_symbol_exposure = current_symbol_exposure + position_size_usd

            if new_symbol_exposure > self.risk_limits.max_exposure_per_pair_usd:
                return ValidationResult(
                    passed=False,
                    reason=f"Symbol exposure limit exceeded: ${new_symbol_exposure} > ${self.risk_limits.max_exposure_per_pair_usd}",
                    risk_level=RiskLevel.MEDIUM,
                )

        return ValidationResult(passed=True)
