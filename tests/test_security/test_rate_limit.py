"""Tests for rate limiting helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from matcher.security.rate_limit import RateLimiter, RedisRateLimiter


class TestRateLimiter:
    def _make_limiter(
        self,
        max_attempts: int = 3,
        window_seconds: int = 60,
        block_seconds: int = 120,
    ) -> RateLimiter:
        return RateLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            block_seconds=block_seconds,
        )

    def test_fresh_key_not_blocked(self):
        """A key that has never been seen should not be blocked."""
        limiter = self._make_limiter()
        assert limiter.is_blocked("192.168.1.1") is False

    def test_blocking_after_max_attempts(self):
        """After recording max_attempts within a window, the key should be blocked."""
        limiter = self._make_limiter(max_attempts=3)
        key = "10.0.0.1"

        for _ in range(3):
            limiter.record_attempt(key)

        assert limiter.is_blocked(key) is True

    def test_block_period_enforcement(self):
        """A blocked key must stay blocked for the entire block_seconds duration."""
        limiter = self._make_limiter(max_attempts=2, block_seconds=300)
        key = "brute_forcer"

        # Exceed limit
        limiter.record_attempt(key)
        limiter.record_attempt(key)
        assert limiter.is_blocked(key) is True

        # Advance time by less than block_seconds -- still blocked
        with patch("matcher.security.rate_limit.time") as mock_time:
            # Simulate 100 seconds after the window_start that was recorded
            entry = limiter._buckets[key]
            mock_time.monotonic.return_value = entry.window_start + 100
            assert limiter.is_blocked(key) is True

    def test_reset_clears_state(self):
        """After reset(), the key should no longer be blocked."""
        limiter = self._make_limiter(max_attempts=2)
        key = "user_ip"

        limiter.record_attempt(key)
        limiter.record_attempt(key)
        assert limiter.is_blocked(key) is True

        limiter.reset(key)
        assert limiter.is_blocked(key) is False

    def test_window_expiry(self):
        """After the sliding window expires, attempt count should reset."""
        limiter = self._make_limiter(max_attempts=3, window_seconds=60, block_seconds=120)
        key = "window_test"

        # Record 2 attempts (below threshold)
        limiter.record_attempt(key)
        limiter.record_attempt(key)
        assert limiter.is_blocked(key) is False

        # Advance time past the window; attempts should reset on next is_blocked check
        with patch("matcher.security.rate_limit.time") as mock_time:
            entry = limiter._buckets[key]
            mock_time.monotonic.return_value = entry.window_start + 61
            assert limiter.is_blocked(key) is False

            # Record a fresh attempt after window reset
            # Need to keep the mock active for record_attempt too
            limiter.record_attempt(key)
            # Should still not be blocked (only 1 attempt in new window)
            assert limiter.is_blocked(key) is False

    def test_block_expires_after_block_seconds(self):
        """After block_seconds have passed, the key should be unblocked."""
        limiter = self._make_limiter(max_attempts=2, block_seconds=120)
        key = "expiry_test"

        limiter.record_attempt(key)
        limiter.record_attempt(key)
        assert limiter.is_blocked(key) is True

        with patch("matcher.security.rate_limit.time") as mock_time:
            entry = limiter._buckets[key]
            # Jump past block_seconds
            mock_time.monotonic.return_value = entry.window_start + 121
            assert limiter.is_blocked(key) is False

    def test_attempts_below_max_not_blocked(self):
        """Recording fewer than max_attempts should not trigger blocking."""
        limiter = self._make_limiter(max_attempts=5)
        key = "partial"

        for _ in range(4):
            limiter.record_attempt(key)

        assert limiter.is_blocked(key) is False


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int | str] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self.values else 0

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, 0))
        current += 1
        self.values[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:  # noqa: ARG002
        self.values[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted


class TestRedisRateLimiter:
    @pytest.mark.asyncio
    async def test_login_blocking_and_reset(self):
        redis = _FakeRedis()
        limiter = RedisRateLimiter(
            prefix="login",
            max_attempts=2,
            window_seconds=60,
            block_seconds=300,
        )

        assert await limiter.is_blocked(redis, "1.2.3.4") is False
        await limiter.record_attempt(redis, "1.2.3.4")
        await limiter.record_attempt(redis, "1.2.3.4")
        assert await limiter.is_blocked(redis, "1.2.3.4") is True

        await limiter.reset(redis, "1.2.3.4")
        assert await limiter.is_blocked(redis, "1.2.3.4") is False

    @pytest.mark.asyncio
    async def test_api_allow_request_enforces_limit(self):
        redis = _FakeRedis()
        limiter = RedisRateLimiter(
            prefix="api",
            max_attempts=2,
            window_seconds=60,
            block_seconds=60,
        )

        assert await limiter.allow_request(redis, "5.6.7.8") is True
        assert await limiter.allow_request(redis, "5.6.7.8") is True
        assert await limiter.allow_request(redis, "5.6.7.8") is False
