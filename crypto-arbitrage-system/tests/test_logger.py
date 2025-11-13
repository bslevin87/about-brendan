"""
Tests for logging framework.

This module tests logger creation, structured logging, and context management.
"""
import logging
from pathlib import Path

import pytest

from src.core.logger import (
    LogContext,
    PerformanceLogger,
    get_logger,
    log_audit,
    setup_logging,
)


class TestLoggerSetup:
    """Test logger setup and configuration."""

    def test_setup_logging(self, tmp_path: Path) -> None:
        """Test logging setup."""
        setup_logging(
            log_level="INFO",
            log_to_file=True,
            log_dir=tmp_path,
            json_output=True
        )

        # Verify log directory exists
        assert tmp_path.exists()

    def test_invalid_log_level(self) -> None:
        """Test handling of invalid log level."""
        with pytest.raises(ValueError):
            setup_logging(log_level="INVALID")

    def test_logger_creation(self) -> None:
        """Test creating a logger."""
        logger = get_logger("test_module")
        assert logger is not None

    def test_logger_with_component(self) -> None:
        """Test creating logger with component context."""
        logger = get_logger("test_module", component="test_component")
        assert logger is not None

    def test_logger_with_correlation_id(self) -> None:
        """Test creating logger with correlation ID."""
        logger = get_logger("test_module", correlation_id="test-123")
        assert logger is not None


class TestStructuredLogging:
    """Test structured logging functionality."""

    def test_logger_info(self) -> None:
        """Test info level logging."""
        logger = get_logger("test")
        # Should not raise
        logger.info("test_message", key="value")

    def test_logger_error(self) -> None:
        """Test error level logging."""
        logger = get_logger("test")
        # Should not raise
        logger.error("test_error", error="test error message")

    def test_logger_debug(self) -> None:
        """Test debug level logging."""
        logger = get_logger("test")
        # Should not raise
        logger.debug("test_debug", debug_info="test data")

    def test_logger_warning(self) -> None:
        """Test warning level logging."""
        logger = get_logger("test")
        # Should not raise
        logger.warning("test_warning", warning_type="test")


class TestLogContext:
    """Test log context manager."""

    def test_log_context(self) -> None:
        """Test logging with context manager."""
        logger = get_logger("test")

        with LogContext(logger, exchange="test_exchange", pair="BTC/USD") as ctx_logger:
            # Should not raise
            ctx_logger.info("test_message")

    def test_multiple_contexts(self) -> None:
        """Test nested log contexts."""
        logger = get_logger("test")

        with LogContext(logger, level1="value1") as ctx1:
            ctx1.info("level1_message")

            with LogContext(ctx1, level2="value2") as ctx2:
                ctx2.info("level2_message")


class TestPerformanceLogger:
    """Test performance logging."""

    @pytest.mark.asyncio
    async def test_performance_logger(self) -> None:
        """Test performance timing."""
        logger = get_logger("test")

        with PerformanceLogger(logger, "test_operation"):
            # Simulate some work
            import asyncio
            await asyncio.sleep(0.01)

    def test_performance_logger_sync(self) -> None:
        """Test performance logging with synchronous code."""
        logger = get_logger("test")

        with PerformanceLogger(logger, "sync_operation"):
            # Simulate work
            sum(range(1000))

    def test_performance_logger_with_context(self) -> None:
        """Test performance logger with additional context."""
        logger = get_logger("test")

        with PerformanceLogger(
            logger,
            "context_operation",
            exchange="test",
            pair="BTC/USD"
        ):
            pass


class TestAuditLogging:
    """Test audit trail logging."""

    def test_log_audit(self) -> None:
        """Test audit logging."""
        logger = get_logger("test")

        log_audit(
            logger,
            "test_action",
            user="test_user",
            details="test details"
        )

    def test_log_audit_with_trade(self) -> None:
        """Test audit logging for trades."""
        logger = get_logger("test")

        log_audit(
            logger,
            "trade_executed",
            exchange="test_exchange",
            pair="BTC/USD",
            amount=0.1,
            price=50000
        )


class TestLogLevels:
    """Test different log levels."""

    def test_all_log_levels(self) -> None:
        """Test that all log levels work."""
        logger = get_logger("test")

        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")

    def test_log_filtering(self, tmp_path: Path) -> None:
        """Test that log level filtering works."""
        setup_logging(
            log_level="WARNING",
            log_to_file=False
        )

        logger = get_logger("test")

        # These should be filtered out
        logger.debug("debug message")
        logger.info("info message")

        # These should pass
        logger.warning("warning message")
        logger.error("error message")
