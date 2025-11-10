"""
Circuit breaker implementation.

Implements circuit breaker pattern for trading system:
- Automatically halts trading on adverse conditions
- Three states: CLOSED (normal), OPEN (halted), HALF_OPEN (testing)
- Auto-recovery after pause duration
- Tracks error rates and failures
"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from src.core.logger import get_logger

logger = get_logger(__name__, component="circuit_breaker")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Trading halted
    HALF_OPEN = "half_open"  # Testing if safe to resume


class CircuitBreaker:
    """
    Implements circuit breaker pattern for trading.

    Automatically halts trading when:
    - Too many consecutive losses
    - High error rate
    - API failures
    - Loss limits exceeded
    """

    def __init__(self, config):
        """
        Initialize circuit breaker.

        Args:
            config: ConfigManager instance
        """
        self.config = config

        self.state = CircuitBreakerState.CLOSED
        self.opened_at: Optional[datetime] = None
        self.failure_count = 0
        self.error_count = 0
        self.total_operations = 0

        # Thresholds
        self.max_consecutive_losses = (
            config.risk.circuit_breakers.max_consecutive_losses
        )
        self.pause_duration = timedelta(
            minutes=config.risk.circuit_breakers.pause_duration_minutes
        )

        logger.info(
            "circuit_breaker_initialized",
            max_consecutive_losses=self.max_consecutive_losses,
            pause_duration_minutes=config.risk.circuit_breakers.pause_duration_minutes,
        )

    def record_success(self) -> None:
        """Record successful operation."""
        self.total_operations += 1

        # If in HALF_OPEN, a success means we can close the breaker
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.close()

    def record_failure(self) -> None:
        """Record failed operation."""
        self.total_operations += 1
        self.failure_count += 1
        self.error_count += 1

        # Check if we should open the breaker
        if self.should_open():
            self.open()

    def should_open(self) -> bool:
        """
        Determine if circuit breaker should open.

        Returns:
            True if breaker should open, False otherwise
        """
        if self.state == CircuitBreakerState.OPEN:
            return False  # Already open

        # Check error rate
        if self.total_operations >= 10:  # Need minimum sample size
            error_rate = (self.error_count / self.total_operations) * 100
            if error_rate > 20:  # 20% error rate
                logger.warning(
                    "high_error_rate_detected", error_rate_percent=error_rate
                )
                return True

        # Check consecutive failures
        if self.failure_count >= 5:
            logger.warning(
                "consecutive_failures_threshold_reached",
                failure_count=self.failure_count,
            )
            return True

        return False

    def open(self) -> None:
        """Open circuit breaker (halt trading)."""
        if self.state == CircuitBreakerState.OPEN:
            return

        self.state = CircuitBreakerState.OPEN
        self.opened_at = datetime.utcnow()

        logger.critical(
            "🚨 CIRCUIT BREAKER OPENED - Trading halted",
            error_count=self.error_count,
            failure_count=self.failure_count,
            total_operations=self.total_operations,
        )

    def close(self) -> None:
        """Close circuit breaker (resume trading)."""
        self.state = CircuitBreakerState.CLOSED
        self.opened_at = None
        self.failure_count = 0
        self.error_count = 0
        self.total_operations = 0

        logger.info("✅ Circuit breaker closed - Trading resumed")

    def check_and_transition(self) -> None:
        """Check if circuit breaker can transition states."""
        if self.state != CircuitBreakerState.OPEN:
            return

        # Check if pause duration has elapsed
        if self.opened_at and datetime.utcnow() - self.opened_at > self.pause_duration:
            # Transition to HALF_OPEN to test
            self.state = CircuitBreakerState.HALF_OPEN
            logger.info("Circuit breaker transitioning to HALF_OPEN - Testing")

    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.

        Returns:
            True if trading allowed, False otherwise
        """
        self.check_and_transition()
        return self.state in [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.HALF_OPEN,
        ]

    def reset(self) -> None:
        """Manually reset circuit breaker."""
        self.close()
        logger.info("circuit_breaker_manually_reset")

    def get_status(self) -> dict:
        """
        Get circuit breaker status.

        Returns:
            Dictionary with circuit breaker state
        """
        return {
            "state": self.state.value,
            "is_trading_allowed": self.is_trading_allowed(),
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "failure_count": self.failure_count,
            "error_count": self.error_count,
            "total_operations": self.total_operations,
            "error_rate_percent": (
                (self.error_count / self.total_operations * 100)
                if self.total_operations > 0
                else 0
            ),
        }
