"""Tests for the in-memory circuit breaker."""

from unittest.mock import patch

from matcher.pipeline.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_fresh_provider_is_available(self):
        cb = CircuitBreaker()
        assert cb.is_available("openai") is True

    def test_failures_below_threshold_remain_available(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure("openai")
        assert cb.is_available("openai") is True

    def test_failures_at_threshold_opens_circuit(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(5):
            cb.record_failure("openai")
        assert cb.is_available("openai") is False

    def test_open_circuit_blocks_during_recovery(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        with patch("matcher.pipeline.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            cb.record_failure("openai")
            cb.record_failure("openai")
            # Circuit is now open until 1060.0
            mock_time.monotonic.return_value = 1030.0
            assert cb.is_available("openai") is False

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        with patch("matcher.pipeline.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            cb.record_failure("openai")
            cb.record_failure("openai")
            # Advance past recovery_timeout
            mock_time.monotonic.return_value = 1061.0
            assert cb.is_available("openai") is True

    def test_success_in_half_open_resets(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        with patch("matcher.pipeline.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            cb.record_failure("openai")
            cb.record_failure("openai")
            # Advance past recovery_timeout — half-open
            mock_time.monotonic.return_value = 1061.0
            assert cb.is_available("openai") is True
            cb.record_success("openai")
            state = cb._get("openai")
            assert state.failures == 0
            assert state.open_until == 0.0

    def test_failure_in_half_open_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        with patch("matcher.pipeline.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            cb.record_failure("openai")
            cb.record_failure("openai")
            # half-open
            mock_time.monotonic.return_value = 1061.0
            assert cb.is_available("openai") is True
            # Another failure reopens
            cb.record_failure("openai")
            state = cb._get("openai")
            assert state.open_until > 1061.0

    def test_multiple_providers_independent(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            cb.record_failure("a")
        assert cb.is_available("a") is False
        assert cb.is_available("b") is True

    def test_custom_thresholds(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10)
        with patch("matcher.pipeline.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            cb.record_failure("openai")
            cb.record_failure("openai")
            # Blocked during 10s window
            mock_time.monotonic.return_value = 105.0
            assert cb.is_available("openai") is False
            # Recovered after 10s
            mock_time.monotonic.return_value = 111.0
            assert cb.is_available("openai") is True
