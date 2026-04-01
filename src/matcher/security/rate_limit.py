"""Simple in-memory rate limiter for brute-force protection."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _BucketEntry:
    attempts: int = 0
    window_start: float = 0.0


class RateLimiter:
    """Token-bucket-style rate limiter keyed by an arbitrary string (e.g., IP address).

    Args:
        max_attempts: Maximum attempts allowed within the window.
        window_seconds: Duration of the sliding window in seconds.
        block_seconds: How long to block after exceeding the limit.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 60,
        block_seconds: int = 300,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._buckets: dict[str, _BucketEntry] = defaultdict(_BucketEntry)

    def is_blocked(self, key: str) -> bool:
        """Check if the key is currently rate-limited."""
        entry = self._buckets.get(key)
        if entry is None:
            return False
        now = time.monotonic()
        elapsed = now - entry.window_start
        if entry.attempts >= self.max_attempts:
            # If still within block period, deny
            if elapsed < self.block_seconds:
                return True
            # Block period expired, reset
            self._buckets[key] = _BucketEntry()
            return False
        # If window expired, reset
        if elapsed > self.window_seconds:
            self._buckets[key] = _BucketEntry()
        return False

    def record_attempt(self, key: str) -> None:
        """Record an authentication attempt for the given key."""
        now = time.monotonic()
        entry = self._buckets[key]
        if entry.window_start == 0.0 or (now - entry.window_start) > self.window_seconds:
            # Reset window
            entry.window_start = now
            entry.attempts = 1
        else:
            entry.attempts += 1

    def reset(self, key: str) -> None:
        """Reset rate limit for a key (e.g., after successful login)."""
        self._buckets.pop(key, None)


# Singleton for login rate limiting: 5 attempts per minute, 5-minute block
login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=60, block_seconds=300)
