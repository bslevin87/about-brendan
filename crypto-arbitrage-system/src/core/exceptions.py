"""
Custom exception classes for the crypto arbitrage system.

This module defines a comprehensive exception hierarchy for handling
various error conditions throughout the application.
"""
from typing import Any, Dict, Optional


class ArbitrageSystemException(Exception):
    """
    Base exception class for all custom exceptions in the system.

    Attributes:
        message: Human-readable error message
        code: Error code for programmatic handling
        details: Additional context about the error
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: Error message describing what went wrong
            code: Optional error code for categorization
            details: Optional dictionary with additional error context
        """
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the exception."""
        if self.details:
            return f"{self.code}: {self.message} | Details: {self.details}"
        return f"{self.code}: {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary format.

        Returns:
            Dictionary representation of the exception
        """
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details
        }


class ConfigurationError(ArbitrageSystemException):
    """
    Raised when there's an error in system configuration.

    Examples:
        - Missing required configuration keys
        - Invalid configuration values
        - YAML parsing errors
        - Environment variable issues
    """
    pass


class ExchangeConnectionError(ArbitrageSystemException):
    """
    Raised when unable to connect to an exchange.

    Examples:
        - Network connectivity issues
        - Exchange API is down
        - Authentication failures
        - Rate limiting exceeded
    """
    pass


class InsufficientBalanceError(ArbitrageSystemException):
    """
    Raised when there's insufficient balance for a trade.

    Examples:
        - Not enough funds to execute trade
        - Balance locked in other positions
        - Withdrawal limits reached
    """
    pass


class RiskLimitExceededError(ArbitrageSystemException):
    """
    Raised when a trade would exceed risk management limits.

    Examples:
        - Position size too large
        - Daily loss limit reached
        - Maximum drawdown exceeded
        - Concentration limits violated
    """
    pass


class ExecutionTimeoutError(ArbitrageSystemException):
    """
    Raised when trade execution takes too long.

    Examples:
        - Order not filled within timeout
        - Exchange response timeout
        - Network latency issues
    """
    pass


class ValidationError(ArbitrageSystemException):
    """
    Raised when data validation fails.

    Examples:
        - Invalid order parameters
        - Malformed API responses
        - Schema validation failures
        - Type checking errors
    """
    pass


class CircuitBreakerTriggeredError(ArbitrageSystemException):
    """
    Raised when a circuit breaker is triggered.

    Examples:
        - Maximum consecutive losses reached
        - Hourly loss limit exceeded
        - System health check failed
        - Emergency stop activated
    """
    pass


class DatabaseError(ArbitrageSystemException):
    """
    Raised when database operations fail.

    Examples:
        - Connection failures
        - Query execution errors
        - Transaction rollback needed
        - Migration issues
    """
    pass


class OrderExecutionError(ArbitrageSystemException):
    """
    Raised when order execution fails.

    Examples:
        - Order rejected by exchange
        - Insufficient liquidity
        - Price slippage too high
        - Order cancellation failed
    """
    pass


class DataFetchError(ArbitrageSystemException):
    """
    Raised when fetching market data fails.

    Examples:
        - Unable to get order book
        - Price feed unavailable
        - WebSocket disconnection
        - Data parsing errors
    """
    pass


class StrategyError(ArbitrageSystemException):
    """
    Raised when strategy execution encounters an error.

    Examples:
        - Invalid strategy parameters
        - Strategy logic errors
        - Signal generation failures
    """
    pass


class ComplianceError(ArbitrageSystemException):
    """
    Raised when compliance checks fail.

    Examples:
        - Transaction limits exceeded
        - Suspicious activity detected
        - Missing audit trail
        - Regulatory violations
    """
    pass


class AuthenticationError(ArbitrageSystemException):
    """
    Raised when authentication fails.

    Examples:
        - Invalid API credentials
        - Expired authentication token
        - Insufficient permissions
        - API key revoked
    """
    pass


class RateLimitError(ArbitrageSystemException):
    """
    Raised when API rate limits are exceeded.

    Examples:
        - Too many requests per second
        - Daily API quota reached
        - Exchange-imposed throttling
    """
    pass


class WithdrawalError(ArbitrageSystemException):
    """
    Raised when withdrawal operations fail.

    Examples:
        - Withdrawal limits exceeded
        - Address validation failed
        - Insufficient balance for fees
        - Exchange withdrawal suspended
    """
    pass


class ArbitrageOpportunityExpiredError(ArbitrageSystemException):
    """
    Raised when an arbitrage opportunity is no longer valid.

    Examples:
        - Price movement eliminated opportunity
        - Opportunity execution took too long
        - Market conditions changed
    """
    pass


# Exception handling utilities

def handle_exception(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = True
) -> Optional[ArbitrageSystemException]:
    """
    Utility function to handle exceptions consistently.

    Args:
        exception: The exception to handle
        context: Additional context about where the error occurred
        reraise: Whether to reraise the exception after handling

    Returns:
        The exception wrapped in ArbitrageSystemException if not reraised

    Raises:
        The original or wrapped exception if reraise is True
    """
    if isinstance(exception, ArbitrageSystemException):
        if context and exception.details:
            exception.details.update(context)
        elif context:
            exception.details = context

        if reraise:
            raise exception
        return exception

    # Wrap non-custom exceptions
    wrapped = ArbitrageSystemException(
        message=str(exception),
        code=exception.__class__.__name__,
        details=context or {}
    )

    if reraise:
        raise wrapped from exception
    return wrapped
