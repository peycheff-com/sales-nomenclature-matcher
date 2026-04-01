"""Simple in-memory circuit breaker for AI provider APIs.

Tracks consecutive failures per provider. After `failure_threshold`
consecutive failures, the circuit opens for `recovery_timeout` seconds.
During open state, `is_available()` returns False so callers can skip
to fallback without waiting for another timeout.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    open_until: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._states: dict[str, _CircuitState] = {}

    def _get(self, provider_id: str) -> _CircuitState:
        if provider_id not in self._states:
            self._states[provider_id] = _CircuitState()
        return self._states[provider_id]

    def is_available(self, provider_id: str) -> bool:
        state = self._get(provider_id)
        if state.open_until == 0.0:
            return True
        if time.monotonic() >= state.open_until:
            # Half-open: allow one request to test recovery
            return True
        return False

    def record_success(self, provider_id: str) -> None:
        state = self._get(provider_id)
        state.failures = 0
        state.open_until = 0.0

    def record_failure(self, provider_id: str) -> None:
        state = self._get(provider_id)
        state.failures += 1
        state.last_failure = time.monotonic()
        if state.failures >= self.failure_threshold:
            state.open_until = time.monotonic() + self.recovery_timeout
            logger.warning(
                "Circuit breaker OPEN for provider %s (failures=%d, recovery in %ds)",
                provider_id,
                state.failures,
                self.recovery_timeout,
            )


# Global instance
provider_circuit = CircuitBreaker()
