"""
Structured logging framework for the crypto arbitrage system.

This module provides a comprehensive logging system using structlog
with support for multiple output formats, log rotation, and contextual logging.
"""
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from structlog.types import FilteringBoundLogger


# Default log directory
DEFAULT_LOG_DIR = Path("logs")


class CorrelationIdProcessor:
    """Processor to add correlation IDs to log entries."""

    def __call__(
        self,
        logger: FilteringBoundLogger,
        method_name: str,
        event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add correlation ID to log entry.

        Args:
            logger: The bound logger instance
            method_name: The name of the log method called
            event_dict: The event dictionary to process

        Returns:
            Modified event dictionary with correlation ID
        """
        if "correlation_id" not in event_dict:
            event_dict["correlation_id"] = str(uuid4())[:8]
        return event_dict


class ComponentProcessor:
    """Processor to ensure component field is always present."""

    def __call__(
        self,
        logger: FilteringBoundLogger,
        method_name: str,
        event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add component to log entry if not present.

        Args:
            logger: The bound logger instance
            method_name: The name of the log method called
            event_dict: The event dictionary to process

        Returns:
            Modified event dictionary with component
        """
        if "component" not in event_dict:
            event_dict["component"] = "system"
        return event_dict


class TimestampProcessor:
    """Processor to add ISO format timestamp."""

    def __call__(
        self,
        logger: FilteringBoundLogger,
        method_name: str,
        event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add ISO format timestamp to log entry.

        Args:
            logger: The bound logger instance
            method_name: The name of the log method called
            event_dict: The event dictionary to process

        Returns:
            Modified event dictionary with timestamp
        """
        event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return event_dict


def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Optional[Path] = None,
    json_output: bool = True,
    rotation_days: int = 7
) -> None:
    """
    Configure the logging system.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to files
        log_dir: Directory for log files
        json_output: Whether to use JSON formatting for file logs
        rotation_days: Number of days to keep log files

    Raises:
        ValueError: If log level is invalid
    """
    # Validate log level
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    # Create log directory if logging to file
    if log_to_file:
        log_dir = log_dir or DEFAULT_LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)

    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        TimestampProcessor(),
        CorrelationIdProcessor(),
        ComponentProcessor(),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on output format
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Setup standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        handlers=[]
    )

    # Add console handler for development
    if os.getenv("ENVIRONMENT", "development") == "development":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logging.root.addHandler(console_handler)

    # Add file handlers if enabled
    if log_to_file and log_dir:
        _setup_file_handlers(log_dir, numeric_level, rotation_days)


def _setup_file_handlers(
    log_dir: Path,
    log_level: int,
    rotation_days: int
) -> None:
    """
    Setup rotating file handlers for different log types.

    Args:
        log_dir: Directory for log files
        log_level: Numeric log level
        rotation_days: Number of days to keep log files
    """
    # Application log (all logs)
    app_log_file = log_dir / "application.log"
    app_handler = logging.handlers.TimedRotatingFileHandler(
        filename=app_log_file,
        when="midnight",
        interval=1,
        backupCount=rotation_days,
        encoding="utf-8"
    )
    app_handler.setLevel(log_level)
    logging.root.addHandler(app_handler)

    # Trades log (INFO and above, trade-specific)
    trades_log_file = log_dir / "trades.log"
    trades_handler = logging.handlers.TimedRotatingFileHandler(
        filename=trades_log_file,
        when="midnight",
        interval=1,
        backupCount=rotation_days * 4,  # Keep trades logs longer
        encoding="utf-8"
    )
    trades_handler.setLevel(logging.INFO)
    trades_handler.addFilter(lambda record: "trade" in record.getMessage().lower())
    logging.root.addHandler(trades_handler)

    # Error log (ERROR and above)
    error_log_file = log_dir / "errors.log"
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=error_log_file,
        when="midnight",
        interval=1,
        backupCount=rotation_days * 4,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    logging.root.addHandler(error_handler)

    # Audit log (INFO and above, audit-specific)
    audit_log_file = log_dir / "audit.log"
    audit_handler = logging.handlers.TimedRotatingFileHandler(
        filename=audit_log_file,
        when="midnight",
        interval=1,
        backupCount=365 * 7,  # Keep audit logs for 7 years
        encoding="utf-8"
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.addFilter(lambda record: "audit" in record.getMessage().lower())
    logging.root.addHandler(audit_handler)


def get_logger(
    name: str,
    component: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance with optional context.

    Args:
        name: Logger name (typically __name__)
        component: Component name for context
        correlation_id: Correlation ID for tracking related log entries

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger(__name__, component="arbitrage_detector")
        >>> logger.info("opportunity_found", pair="BTC/USD", profit=0.45)
    """
    logger = structlog.get_logger(name)

    # Bind context if provided
    if component:
        logger = logger.bind(component=component)
    if correlation_id:
        logger = logger.bind(correlation_id=correlation_id)

    return logger


class LogContext:
    """
    Context manager for adding temporary context to logs.

    Example:
        >>> logger = get_logger(__name__)
        >>> with LogContext(logger, exchange="kraken", pair="BTC/USD") as ctx_logger:
        >>>     ctx_logger.info("fetching_orderbook")
        >>>     # All logs within this context will include exchange and pair
    """

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        **context: Any
    ) -> None:
        """
        Initialize log context.

        Args:
            logger: Logger to add context to
            **context: Key-value pairs to add as context
        """
        self.logger = logger
        self.context = context
        self.bound_logger: Optional[structlog.stdlib.BoundLogger] = None

    def __enter__(self) -> structlog.stdlib.BoundLogger:
        """Enter context and return logger with bound context."""
        self.bound_logger = self.logger.bind(**self.context)
        return self.bound_logger

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context."""
        pass


class PerformanceLogger:
    """
    Context manager for logging performance metrics.

    Example:
        >>> logger = get_logger(__name__)
        >>> with PerformanceLogger(logger, "fetch_prices"):
        >>>     # code to measure
        >>>     fetch_prices_from_exchange()
    """

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        operation: str,
        **context: Any
    ) -> None:
        """
        Initialize performance logger.

        Args:
            logger: Logger to use
            operation: Name of the operation being measured
            **context: Additional context to include
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: Optional[datetime] = None

    def __enter__(self) -> "PerformanceLogger":
        """Start timing the operation."""
        self.start_time = datetime.utcnow()
        self.logger.debug(
            "operation_started",
            operation=self.operation,
            **self.context
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Log operation completion time."""
        if self.start_time:
            duration = (datetime.utcnow() - self.start_time).total_seconds()
            self.logger.info(
                "operation_completed",
                operation=self.operation,
                duration_seconds=duration,
                success=exc_type is None,
                **self.context
            )


# Convenience function to log audit trail
def log_audit(
    logger: structlog.stdlib.BoundLogger,
    action: str,
    **details: Any
) -> None:
    """
    Log an audit trail entry.

    Args:
        logger: Logger to use
        action: Action being audited
        **details: Additional details about the action

    Example:
        >>> logger = get_logger(__name__)
        >>> log_audit(logger, "trade_executed", exchange="kraken",
        ...           pair="BTC/USD", amount=0.1, price=50000)
    """
    logger.info(
        "audit",
        action=action,
        audit_type="compliance",
        **details
    )


# Initialize default logging on import
def initialize_default_logging() -> None:
    """Initialize default logging configuration."""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    log_rotation_days = int(os.getenv("LOG_ROTATION_DAYS", "7"))

    setup_logging(
        log_level=log_level,
        log_to_file=log_to_file,
        rotation_days=log_rotation_days
    )


# Auto-initialize if LOG_LEVEL is set
if os.getenv("LOG_LEVEL"):
    initialize_default_logging()
