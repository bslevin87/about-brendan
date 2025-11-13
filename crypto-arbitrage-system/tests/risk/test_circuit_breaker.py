"""
Tests for circuit breaker.

Tests:
- State transitions
- Error threshold triggering
- Automatic recovery
- Manual reset
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create mock config
        self.config = MagicMock()
        self.config.risk.circuit_breakers.max_consecutive_losses = 5
        self.config.risk.circuit_breakers.pause_duration_minutes = 5

        self.breaker = CircuitBreaker(self.config)

    def test_initialization(self):
        """Test circuit breaker initialization."""
        assert self.breaker.state == CircuitBreakerState.CLOSED
        assert self.breaker.is_trading_allowed()

    def test_record_success(self):
        """Test recording successful operations."""
        self.breaker.record_success()
        assert self.breaker.total_operations == 1
        assert self.breaker.error_count == 0

    def test_record_failure(self):
        """Test recording failed operations."""
        self.breaker.record_failure()
        assert self.breaker.total_operations == 1
        assert self.breaker.error_count == 1
        assert self.breaker.failure_count == 1

    def test_open_on_consecutive_failures(self):
        """Test breaker opens on consecutive failures."""
        # Record 5 consecutive failures
        for _ in range(5):
            self.breaker.record_failure()

        # Breaker should open
        assert self.breaker.state == CircuitBreakerState.OPEN
        assert not self.breaker.is_trading_allowed()

    def test_open_on_high_error_rate(self):
        """Test breaker opens on high error rate."""
        # 3 successes, 7 failures = 70% error rate (> 20% threshold)
        for _ in range(3):
            self.breaker.record_success()
        for _ in range(7):
            self.breaker.record_failure()

        # Breaker should open due to high error rate
        assert self.breaker.state == CircuitBreakerState.OPEN

    def test_manual_reset(self):
        """Test manual reset."""
        # Open the breaker
        for _ in range(5):
            self.breaker.record_failure()
        assert self.breaker.state == CircuitBreakerState.OPEN

        # Manual reset
        self.breaker.reset()
        assert self.breaker.state == CircuitBreakerState.CLOSED
        assert self.breaker.is_trading_allowed()
        assert self.breaker.error_count == 0

    def test_half_open_transition(self):
        """Test transition to HALF_OPEN after pause."""
        # Open the breaker
        for _ in range(5):
            self.breaker.record_failure()
        assert self.breaker.state == CircuitBreakerState.OPEN

        # Simulate pause duration passing
        self.breaker.opened_at = datetime.utcnow() - timedelta(minutes=10)
        self.breaker.check_and_transition()

        # Should transition to HALF_OPEN
        assert self.breaker.state == CircuitBreakerState.HALF_OPEN
        assert self.breaker.is_trading_allowed()

    def test_half_open_to_closed_on_success(self):
        """Test HALF_OPEN to CLOSED on successful operation."""
        # Open the breaker
        for _ in range(5):
            self.breaker.record_failure()

        # Transition to HALF_OPEN
        self.breaker.opened_at = datetime.utcnow() - timedelta(minutes=10)
        self.breaker.check_and_transition()
        assert self.breaker.state == CircuitBreakerState.HALF_OPEN

        # Record success in HALF_OPEN
        self.breaker.record_success()

        # Should close
        assert self.breaker.state == CircuitBreakerState.CLOSED

    def test_get_status(self):
        """Test status retrieval."""
        self.breaker.record_success()
        self.breaker.record_failure()

        status = self.breaker.get_status()

        assert status["state"] == "closed"
        assert status["is_trading_allowed"]
        assert status["total_operations"] == 2
        assert status["error_count"] == 1
        assert "error_rate_percent" in status
