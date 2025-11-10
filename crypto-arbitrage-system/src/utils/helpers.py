"""
Common utility functions for the crypto arbitrage system.

This module provides reusable helper functions for common operations
like formatting, calculations, validation, and conversions.
"""
import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4


def generate_id(prefix: str = "") -> str:
    """
    Generate a unique ID with optional prefix.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        Unique ID string

    Example:
        >>> generate_id("trade")
        'trade_a1b2c3d4'
    """
    unique_id = uuid4().hex[:8]
    return f"{prefix}_{unique_id}" if prefix else unique_id


def utc_now() -> datetime:
    """
    Get current UTC datetime with timezone info.

    Returns:
        Current UTC datetime
    """
    return datetime.now(timezone.utc)


def format_price(price: Union[Decimal, float], decimals: int = 2) -> str:
    """
    Format price for display.

    Args:
        price: Price to format
        decimals: Number of decimal places

    Returns:
        Formatted price string

    Example:
        >>> format_price(1234.56789, 2)
        '$1,234.57'
    """
    price_decimal = Decimal(str(price))
    quantized = price_decimal.quantize(Decimal(10) ** -decimals)
    return f"${quantized:,.{decimals}f}"


def format_percent(value: Union[Decimal, float], decimals: int = 2) -> str:
    """
    Format percentage for display.

    Args:
        value: Decimal value (e.g., 0.05 for 5%)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string

    Example:
        >>> format_percent(0.0545, 2)
        '5.45%'
    """
    percent = Decimal(str(value)) * 100
    return f"{percent:.{decimals}f}%"


def round_down(value: Union[Decimal, float], decimals: int) -> Decimal:
    """
    Round value down to specified decimal places.

    Args:
        value: Value to round
        decimals: Number of decimal places

    Returns:
        Rounded down Decimal

    Example:
        >>> round_down(1.23456, 2)
        Decimal('1.23')
    """
    decimal_value = Decimal(str(value))
    quantize_to = Decimal(10) ** -decimals
    return decimal_value.quantize(quantize_to, rounding=ROUND_DOWN)


def round_up(value: Union[Decimal, float], decimals: int) -> Decimal:
    """
    Round value up to specified decimal places.

    Args:
        value: Value to round
        decimals: Number of decimal places

    Returns:
        Rounded up Decimal

    Example:
        >>> round_up(1.23456, 2)
        Decimal('1.24')
    """
    decimal_value = Decimal(str(value))
    quantize_to = Decimal(10) ** -decimals
    return decimal_value.quantize(quantize_to, rounding=ROUND_UP)


def calculate_profit_percent(
    buy_price: Union[Decimal, float],
    sell_price: Union[Decimal, float],
    fees_percent: Union[Decimal, float] = 0
) -> Decimal:
    """
    Calculate profit percentage after fees.

    Args:
        buy_price: Purchase price
        sell_price: Sell price
        fees_percent: Total fees as decimal (e.g., 0.002 for 0.2%)

    Returns:
        Profit percentage as decimal

    Example:
        >>> calculate_profit_percent(100, 101, 0.001)
        Decimal('0.008')  # 0.8% profit
    """
    buy = Decimal(str(buy_price))
    sell = Decimal(str(sell_price))
    fees = Decimal(str(fees_percent))

    gross_profit = (sell - buy) / buy
    net_profit = gross_profit - fees
    return net_profit


def calculate_position_size(
    capital: Union[Decimal, float],
    price: Union[Decimal, float],
    max_position_percent: Union[Decimal, float]
) -> Decimal:
    """
    Calculate maximum position size based on capital and risk limits.

    Args:
        capital: Available capital
        price: Current price
        max_position_percent: Maximum position size as decimal (e.g., 0.10 for 10%)

    Returns:
        Maximum position size in units

    Example:
        >>> calculate_position_size(10000, 50000, 0.25)
        Decimal('0.05')  # Can buy 0.05 BTC
    """
    cap = Decimal(str(capital))
    p = Decimal(str(price))
    max_pct = Decimal(str(max_position_percent))

    max_value = cap * max_pct
    return max_value / p


def validate_pair(pair: str) -> bool:
    """
    Validate trading pair format.

    Args:
        pair: Trading pair (e.g., "BTC/USD")

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_pair("BTC/USD")
        True
        >>> validate_pair("BTCUSD")
        False
    """
    pattern = r"^[A-Z]{2,10}/[A-Z]{2,10}$"
    return bool(re.match(pattern, pair))


def parse_pair(pair: str) -> tuple[str, str]:
    """
    Parse trading pair into base and quote currencies.

    Args:
        pair: Trading pair (e.g., "BTC/USD")

    Returns:
        Tuple of (base, quote)

    Raises:
        ValueError: If pair format is invalid

    Example:
        >>> parse_pair("BTC/USD")
        ('BTC', 'USD')
    """
    if not validate_pair(pair):
        raise ValueError(f"Invalid pair format: {pair}")

    base, quote = pair.split("/")
    return base, quote


def calculate_fees(
    amount: Union[Decimal, float],
    fee_percent: Union[Decimal, float]
) -> Decimal:
    """
    Calculate fee amount.

    Args:
        amount: Transaction amount
        fee_percent: Fee percentage as decimal (e.g., 0.001 for 0.1%)

    Returns:
        Fee amount

    Example:
        >>> calculate_fees(1000, 0.001)
        Decimal('1.00')
    """
    amt = Decimal(str(amount))
    fee = Decimal(str(fee_percent))
    return amt * fee


def calculate_slippage(
    expected_price: Union[Decimal, float],
    executed_price: Union[Decimal, float]
) -> Decimal:
    """
    Calculate slippage percentage.

    Args:
        expected_price: Expected execution price
        executed_price: Actual execution price

    Returns:
        Slippage as decimal (negative means worse execution)

    Example:
        >>> calculate_slippage(100, 101)
        Decimal('-0.01')  # 1% negative slippage
    """
    expected = Decimal(str(expected_price))
    executed = Decimal(str(executed_price))

    if expected == 0:
        return Decimal("0")

    return (expected - executed) / expected


def hash_data(data: str) -> str:
    """
    Create SHA-256 hash of data.

    Args:
        data: Data to hash

    Returns:
        Hexadecimal hash string

    Example:
        >>> hash_data("test")
        '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
    """
    return hashlib.sha256(data.encode()).hexdigest()


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize dictionary by removing sensitive keys.

    Args:
        data: Dictionary to sanitize

    Returns:
        Sanitized dictionary with sensitive values redacted

    Example:
        >>> sanitize_dict({"user": "john", "api_key": "secret"})
        {'user': 'john', 'api_key': '***REDACTED***'}
    """
    sensitive_keys = {
        "api_key",
        "api_secret",
        "password",
        "secret",
        "token",
        "private_key",
        "passphrase",
    }

    sanitized = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        else:
            sanitized[key] = value

    return sanitized


def chunks(lst: List[Any], n: int) -> List[List[Any]]:
    """
    Split list into chunks of size n.

    Args:
        lst: List to split
        n: Chunk size

    Returns:
        List of chunks

    Example:
        >>> chunks([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def safe_divide(
    numerator: Union[Decimal, float],
    denominator: Union[Decimal, float],
    default: Union[Decimal, float] = 0
) -> Decimal:
    """
    Safely divide two numbers, returning default if denominator is zero.

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if division by zero

    Returns:
        Result or default

    Example:
        >>> safe_divide(10, 2)
        Decimal('5')
        >>> safe_divide(10, 0, default=0)
        Decimal('0')
    """
    num = Decimal(str(numerator))
    denom = Decimal(str(denominator))
    default_val = Decimal(str(default))

    if denom == 0:
        return default_val
    return num / denom


def clamp(
    value: Union[Decimal, float],
    min_value: Union[Decimal, float],
    max_value: Union[Decimal, float]
) -> Decimal:
    """
    Clamp value between min and max.

    Args:
        value: Value to clamp
        min_value: Minimum value
        max_value: Maximum value

    Returns:
        Clamped value

    Example:
        >>> clamp(5, 0, 10)
        Decimal('5')
        >>> clamp(15, 0, 10)
        Decimal('10')
    """
    val = Decimal(str(value))
    min_val = Decimal(str(min_value))
    max_val = Decimal(str(max_value))

    return max(min_val, min(val, max_val))


def is_valid_exchange_name(exchange: str) -> bool:
    """
    Validate exchange name format.

    Args:
        exchange: Exchange name to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_exchange_name("kraken")
        True
        >>> is_valid_exchange_name("invalid exchange!")
        False
    """
    pattern = r"^[a-z0-9_]+$"
    return bool(re.match(pattern, exchange))


def normalize_exchange_name(exchange: str) -> str:
    """
    Normalize exchange name to standard format.

    Args:
        exchange: Exchange name to normalize

    Returns:
        Normalized exchange name (lowercase, underscores)

    Example:
        >>> normalize_exchange_name("Binance.US")
        'binance_us'
    """
    # Replace dots with underscores
    normalized = exchange.replace(".", "_")
    # Convert to lowercase
    normalized = normalized.lower()
    # Remove any non-alphanumeric characters except underscores
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    return normalized


def time_ago(dt: datetime) -> str:
    """
    Get human-readable time difference from now.

    Args:
        dt: Datetime to compare

    Returns:
        Human-readable time difference

    Example:
        >>> from datetime import timedelta
        >>> time_ago(utc_now() - timedelta(seconds=30))
        '30 seconds ago'
    """
    now = utc_now()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)} hours ago"
    else:
        return f"{int(seconds / 86400)} days ago"


def truncate_string(s: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate string to maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string

    Example:
        >>> truncate_string("This is a very long string", 10)
        'This is...'
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix
