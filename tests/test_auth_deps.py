from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from matcher.auth import deps
from matcher.db.models import User


def _request(
    *,
    method: str = "GET",
    path: str = "/api/v1/catalog/products",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": raw_headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _active_user(**overrides) -> User:
    values = {
        "user_id": "usr_1",
        "username": "alice",
        "hashed_password": "hash",
        "role": "operator",
        "is_active": True,
        "must_change_password": False,
    }
    values.update(overrides)
    return User(**values)


def test_extract_token_prefers_cookie_then_header():
    request = _request(cookies={deps.ACCESS_TOKEN_COOKIE: "cookie-token"})
    assert deps._extract_token(request, "header-token") == "cookie-token"

    request = _request()
    assert deps._extract_token(request, "header-token") == "header-token"
    assert deps._extract_token(request, None) is None


def test_validate_csrf_allows_safe_exempt_header_and_double_submit_requests():
    deps._validate_csrf(_request(method="GET", cookies={deps.ACCESS_TOKEN_COOKIE: "jwt"}))
    deps._validate_csrf(
        _request(
            method="POST",
            path="/api/v1/auth/login",
            cookies={deps.ACCESS_TOKEN_COOKIE: "jwt"},
        )
    )
    deps._validate_csrf(_request(method="POST"))
    deps._validate_csrf(
        _request(
            method="POST",
            headers={deps.CSRF_HEADER: "csrf"},
            cookies={deps.ACCESS_TOKEN_COOKIE: "jwt", deps.CSRF_TOKEN_COOKIE: "csrf"},
        )
    )


def test_validate_csrf_allows_same_origin_and_same_referer():
    deps._validate_csrf(
        _request(
            method="POST",
            headers={"host": "app.example.com", "origin": "https://app.example.com"},
            cookies={deps.ACCESS_TOKEN_COOKIE: "jwt"},
        )
    )
    deps._validate_csrf(
        _request(
            method="POST",
            headers={"host": "app.example.com:443", "referer": "https://app.example.com/form"},
            cookies={deps.ACCESS_TOKEN_COOKIE: "jwt"},
        )
    )


def test_validate_csrf_rejects_cookie_authenticated_cross_site_mutation():
    with pytest.raises(HTTPException) as exc_info:
        deps._validate_csrf(
            _request(
                method="DELETE",
                headers={"host": "app.example.com", "origin": "https://evil.example.net"},
                cookies={deps.ACCESS_TOKEN_COOKIE: "jwt"},
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "CSRF validation failed"


@pytest.mark.asyncio
async def test_get_current_user_validates_token_and_loads_active_user(
    monkeypatch: pytest.MonkeyPatch,
):
    user = _active_user()
    repo = SimpleNamespace(get_by_username=AsyncMock(return_value=user))
    monkeypatch.setattr(deps, "decode_access_token", lambda token: {"sub": "alice"})
    monkeypatch.setattr(deps, "UserRepo", lambda db: repo)

    result = await deps.get_current_user(_request(), header_token="jwt", db=object())

    assert result is user
    repo.get_by_username.assert_awaited_once_with("alice")


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_invalid_or_unknown_users(
    monkeypatch: pytest.MonkeyPatch,
):
    with pytest.raises(HTTPException) as missing_token:
        await deps.get_current_user(_request(), header_token=None, db=object())
    assert missing_token.value.status_code == 401

    def missing_subject(_token):
        return {}

    monkeypatch.setattr(deps, "decode_access_token", missing_subject)
    with pytest.raises(HTTPException) as missing_sub:
        await deps.get_current_user(_request(), header_token="jwt", db=object())
    assert missing_sub.value.status_code == 401

    def invalid_token(_token):
        raise deps.InvalidTokenError("bad")

    monkeypatch.setattr(deps, "decode_access_token", invalid_token)
    with pytest.raises(HTTPException) as invalid:
        await deps.get_current_user(_request(), header_token="jwt", db=object())
    assert invalid.value.status_code == 401

    repo = SimpleNamespace(get_by_username=AsyncMock(return_value=None))
    monkeypatch.setattr(deps, "decode_access_token", lambda token: {"sub": "alice"})
    monkeypatch.setattr(deps, "UserRepo", lambda db: repo)
    with pytest.raises(HTTPException) as missing_user:
        await deps.get_current_user(_request(), header_token="jwt", db=object())
    assert missing_user.value.status_code == 401

    repo.get_by_username = AsyncMock(return_value=_active_user(is_active=False))
    with pytest.raises(HTTPException) as inactive_user:
        await deps.get_current_user(_request(), header_token="jwt", db=object())
    assert inactive_user.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_enforces_password_change_gate(
    monkeypatch: pytest.MonkeyPatch,
):
    user = _active_user(must_change_password=True)
    repo = SimpleNamespace(get_by_username=AsyncMock(return_value=user))
    monkeypatch.setattr(deps, "decode_access_token", lambda token: {"sub": "alice"})
    monkeypatch.setattr(deps, "UserRepo", lambda db: repo)

    with pytest.raises(HTTPException) as blocked:
        await deps.get_current_user(
            _request(path="/api/v1/catalog/products"),
            header_token="jwt",
            db=object(),
        )
    assert blocked.value.status_code == 403
    assert blocked.value.detail == "Password change required"

    allowed = await deps.get_current_user(
        _request(path="/api/v1/auth/me"),
        header_token="jwt",
        db=object(),
    )
    assert allowed is user


@pytest.mark.asyncio
async def test_require_role_allows_matching_role_and_rejects_others():
    check_admin = deps.require_role("admin", "operator")

    operator = _active_user(role="operator")
    assert await check_admin(operator) is operator

    viewer = _active_user(role="viewer")
    with pytest.raises(HTTPException) as denied:
        await check_admin(viewer)

    assert denied.value.status_code == 403
    assert denied.value.detail == "Insufficient permissions"
