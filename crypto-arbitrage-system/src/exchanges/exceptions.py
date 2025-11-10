"""
Exchange-specific exceptions.

This module defines exceptions for handling exchange-related errors.
"""
from typing import Any, Dict, Optional


class ExchangeException(Exception):
    """
    Base exception for all exchange-related errors.

    Attributes:
        message: Human-readable error message
        exchange: Exchange name where error occurred
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize exchange exception.

        Args:
            message: Error message
            exchange: Exchange name
            details: Additional error details
        """
        self.message = message
        self.exchange = exchange
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation."""
        base = f"[{self.exchange}] {self.message}" if self.exchange else self.message
        if self.details:
            return f"{base} | Details: {self.details}"
        return base


class AuthenticationError(ExchangeException):
    """
    Raised when API authentication fails.

    Examples:
        - Invalid API key
        - Invalid API secret
        - Expired authentication token
        - Missing required authentication headers
        - Invalid signature
    """
    pass


class RateLimitExceeded(ExchangeException):
    """
    Raised when exchange rate limit is exceeded.

    Examples:
        - Too many requests per second
        - Daily/hourly API quota exceeded
        - IP-based rate limiting
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize rate limit exception.

        Args:
            message: Error message
            exchange: Exchange name
            retry_after: Seconds to wait before retrying
            details: Additional details
        """
        super().__init__(message, exchange, details)
        self.retry_after = retry_after


class InsufficientFundsError(ExchangeException):
    """
    Raised when account has insufficient funds for operation.

    Examples:
        - Not enough balance to place order
        - Funds locked in other orders
        - Below minimum order size
        - Withdrawal amount exceeds available balance
    """
    pass


class InvalidOrderError(ExchangeException):
    """
    Raised when order parameters are invalid.

    Examples:
        - Invalid trading pair
        - Order size below minimum
        - Order size above maximum
        - Invalid price (e.g., negative)
        - Limit price too far from market
    """
    pass


class OrderNotFoundError(ExchangeException):
    """
    Raised when order ID doesn't exist.

    Examples:
        - Order already cancelled
        - Order already filled
        - Invalid order ID
        - Order belongs to different account
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        order_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize order not found exception.

        Args:
            message: Error message
            exchange: Exchange name
            order_id: Order ID that wasn't found
            details: Additional details
        """
        super().__init__(message, exchange, details)
        self.order_id = order_id


class ExchangeUnavailableError(ExchangeException):
    """
    Raised when exchange is down or unreachable.

    Examples:
        - Exchange API is down
        - Scheduled maintenance
        - Network connectivity issues
        - DNS resolution failures
        - Timeouts
    """
    pass


class WebSocketError(ExchangeException):
    """
    Raised when WebSocket connection encounters an error.

    Examples:
        - Connection failed
        - Connection closed unexpectedly
        - Subscription failed
        - Message parsing error
        - Authentication failed on WebSocket
    """
    pass


class MarketClosedError(ExchangeException):
    """
    Raised when attempting to trade on a closed market.

    Examples:
        - Trading pair suspended
        - Market temporarily disabled
        - Maintenance mode
    """
    pass


class InvalidSymbolError(ExchangeException):
    """
    Raised when trading pair/symbol is invalid or not supported.

    Examples:
        - Symbol not found on exchange
        - Invalid symbol format
        - Delisted trading pair
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize invalid symbol exception.

        Args:
            message: Error message
            exchange: Exchange name
            symbol: Invalid symbol
            details: Additional details
        """
        super().__init__(message, exchange, details)
        self.symbol = symbol


class NetworkError(ExchangeException):
    """
    Raised when network-related errors occur.

    Examples:
        - Connection timeout
        - SSL/TLS errors
        - DNS failures
        - Proxy errors
    """
    pass


class ExchangeMaintenanceError(ExchangeException):
    """
    Raised when exchange is under maintenance.

    Examples:
        - Scheduled maintenance
        - Emergency maintenance
        - System upgrade
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        estimated_end_time: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize maintenance exception.

        Args:
            message: Error message
            exchange: Exchange name
            estimated_end_time: When maintenance is expected to end
            details: Additional details
        """
        super().__init__(message, exchange, details)
        self.estimated_end_time = estimated_end_time


class OrderRejectError(ExchangeException):
    """
    Raised when order is rejected by exchange.

    Examples:
        - Post-only order would match immediately
        - Self-trade prevention triggered
        - Risk management rules violated
        - Account restrictions
    """
    pass


class WithdrawalError(ExchangeException):
    """
    Raised when withdrawal operation fails.

    Examples:
        - Withdrawal disabled for asset
        - Below minimum withdrawal amount
        - Invalid destination address
        - Withdrawal limits exceeded
        - Pending withdrawal already exists
    """
    pass


class APIError(ExchangeException):
    """
    Raised for generic API errors.

    Use this for exchange-specific errors that don't fit other categories.
    """

    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize API error exception.

        Args:
            message: Error message
            exchange: Exchange name
            status_code: HTTP status code
            error_code: Exchange-specific error code
            details: Additional details
        """
        super().__init__(message, exchange, details)
        self.status_code = status_code
        self.error_code = error_code


# Utility function to map exchange error codes to exceptions
def map_exchange_error(
    exchange: str,
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> ExchangeException:
    """
    Map exchange-specific error codes to appropriate exception types.

    Args:
        exchange: Exchange name
        error_code: Exchange error code
        message: Error message
        details: Additional error details

    Returns:
        Appropriate ExchangeException subclass

    Example:
        >>> error = map_exchange_error("kraken", "EAPI:Invalid key", "Authentication failed")
        >>> raise error
    """
    # Common error code patterns
    auth_patterns = ["auth", "key", "signature", "permission", "unauthorized"]
    rate_patterns = ["rate", "limit", "throttle", "too many"]
    funds_patterns = ["insufficient", "balance", "funds"]
    order_patterns = ["order", "invalid"]
    network_patterns = ["timeout", "network", "connection", "unreachable"]

    error_lower = error_code.lower() + " " + message.lower()

    if any(pattern in error_lower for pattern in auth_patterns):
        return AuthenticationError(message, exchange, details)
    elif any(pattern in error_lower for pattern in rate_patterns):
        return RateLimitExceeded(message, exchange, details=details)
    elif any(pattern in error_lower for pattern in funds_patterns):
        return InsufficientFundsError(message, exchange, details)
    elif any(pattern in error_lower for pattern in order_patterns):
        return InvalidOrderError(message, exchange, details)
    elif any(pattern in error_lower for pattern in network_patterns):
        return NetworkError(message, exchange, details)
    else:
        return APIError(message, exchange, error_code=error_code, details=details)
