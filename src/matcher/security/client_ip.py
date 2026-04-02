from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Return the best-effort client IP behind a trusted reverse proxy."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip

    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"
