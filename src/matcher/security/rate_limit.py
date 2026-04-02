"""Rate limiting helpers.

`RateLimiter` remains as an in-memory fallback/test helper.
`RedisRateLimiter` is the production path shared by all API workers.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from arq import ArqRedis


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


class RedisRateLimiter:
    """Redis-backed shared rate limiter."""

    def __init__(
        self,
        *,
        prefix: str,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
    ) -> None:
        self.prefix = prefix
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds

    def _attempts_key(self, key: str) -> str:
        return f"ratelimit:{self.prefix}:attempts:{key}"

    def _blocked_key(self, key: str) -> str:
        return f"ratelimit:{self.prefix}:blocked:{key}"

    async def is_blocked(self, redis: ArqRedis, key: str) -> bool:
        return bool(await redis.exists(self._blocked_key(key)))

    async def record_attempt(self, redis: ArqRedis, key: str) -> int:
        blocked_key = self._blocked_key(key)
        attempts_key = self._attempts_key(key)

        count = await redis.incr(attempts_key)
        if count == 1:
            await redis.expire(attempts_key, self.window_seconds)

        if count >= self.max_attempts:
            await redis.set(blocked_key, "1", ex=self.block_seconds)
        return count

    async def reset(self, redis: ArqRedis, key: str) -> None:
        await redis.delete(self._attempts_key(key), self._blocked_key(key))

    async def allow_request(self, redis: ArqRedis, key: str) -> bool:
        attempts_key = self._attempts_key(key)
        count = await redis.incr(attempts_key)
        if count == 1:
            await redis.expire(attempts_key, self.window_seconds)
        return count <= self.max_attempts


login_rate_limiter = RedisRateLimiter(
    prefix="login",
    max_attempts=5,
    window_seconds=60,
    block_seconds=300,
)

api_rate_limiter = RedisRateLimiter(
    prefix="api",
    max_attempts=60,
    window_seconds=60,
    block_seconds=60,
)
