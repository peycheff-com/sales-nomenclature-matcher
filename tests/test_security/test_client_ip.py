from __future__ import annotations

from types import SimpleNamespace

from starlette.datastructures import Headers

from matcher.security.client_ip import get_client_ip


def _request(headers: dict[str, str] | None = None, client_host: str | None = "127.0.0.1"):
    client = SimpleNamespace(host=client_host) if client_host is not None else None
    return SimpleNamespace(headers=Headers(headers or {}), client=client)


def test_get_client_ip_prefers_first_forwarded_for_value():
    request = _request({"X-Forwarded-For": "203.0.113.10, 10.0.0.5"})

    assert get_client_ip(request) == "203.0.113.10"


def test_get_client_ip_falls_back_to_real_ip_when_forwarded_for_is_blank():
    request = _request({"X-Forwarded-For": " , 10.0.0.5", "X-Real-IP": "203.0.113.20"})

    assert get_client_ip(request) == "203.0.113.20"


def test_get_client_ip_falls_back_to_request_client():
    request = _request(client_host="198.51.100.7")

    assert get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_returns_unknown_when_no_source_exists():
    request = _request(client_host=None)

    assert get_client_ip(request) == "unknown"
