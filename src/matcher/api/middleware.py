from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from matcher.config import settings
from matcher.logging_config import request_id_var
from matcher.security.rate_limit import api_rate_limiter

logger = logging.getLogger(__name__)

_TIMEOUT_EXEMPT = frozenset({"/api/v1/health"})
_RATE_LIMIT_EXEMPT = frozenset({"/api/v1/health", "/metrics"})


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        request_id_var.set(req_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = req_id

        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting for all API endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _RATE_LIMIT_EXEMPT:
            return await call_next(request)

        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        ).split(",")[0].strip()

        if api_rate_limiter.is_blocked(client_ip):
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "detail": "Rate limit exceeded. Try again later."},
            )
        api_rate_limiter.record_attempt(client_ip)
        return await call_next(request)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Abort requests that exceed the configured timeout."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _TIMEOUT_EXEMPT:
            return await call_next(request)
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=settings.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Request timeout (%ds): %s %s",
                settings.request_timeout_seconds,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=504,
                content={"error": "Gateway Timeout", "detail": "Request processing timed out."},
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defense-in-depth security headers to all API responses.

    These complement nginx headers and protect the API when accessed directly
    (e.g., in development or if nginx is bypassed).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-XSS-Protection"] = "0"  # Disabled per modern best practice
        return response
