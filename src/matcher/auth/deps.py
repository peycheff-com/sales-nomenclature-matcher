from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.security import decode_access_token
from matcher.db.models import User
from matcher.db.repos.user import UserRepo

logger = logging.getLogger(__name__)

# Keep OAuth2 scheme for OpenAPI "Authorize" button (dev convenience)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Cookie name — must match auth.py
ACCESS_TOKEN_COOKIE = "access_token"
CSRF_TOKEN_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# Methods that mutate state and require CSRF validation
CSRF_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Routes exempt from CSRF (login itself uses form-based auth, not cookie)
CSRF_EXEMPT_PATHS = frozenset({"/api/v1/auth/login"})


def _extract_token(request: Request, header_token: str | None) -> str | None:
    """Extract JWT from cookie first, then fallback to Authorization header.

    Priority: httpOnly cookie → Bearer header (for API clients / migration)
    """
    # 1. Try httpOnly cookie
    cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if cookie_token:
        return cookie_token

    # 2. Fallback: Authorization header (backward compat for API consumers)
    if header_token:
        return header_token

    return None


def _validate_csrf(request: Request) -> None:
    """Validate CSRF token for cookie-authenticated mutating requests.

    Two-layer defense:
    1. Double-submit cookie (csrf_token cookie == X-CSRF-Token header)
    2. Origin/Referer validation (same-origin check)

    Either passing is sufficient — layer 2 is the fallback for dev proxies
    where JS may not see the cookie.
    """
    if request.method not in CSRF_PROTECTED_METHODS:
        return

    if request.url.path in CSRF_EXEMPT_PATHS:
        return

    # If request used Authorization header (not cookie), skip CSRF
    # API clients using Bearer tokens don't need CSRF protection
    cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not cookie_token:
        return

    # Layer 1: double-submit cookie
    csrf_cookie = request.cookies.get(CSRF_TOKEN_COOKIE)
    csrf_header = request.headers.get(CSRF_HEADER)
    if csrf_cookie and csrf_header and csrf_cookie == csrf_header:
        return  # Valid double-submit

    # Layer 2: Origin / Referer same-origin check (OWASP recommended)
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    host = request.headers.get("host", "")

    if origin:
        # Origin header present — verify it matches our host
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        origin_host = parsed.netloc
        if origin_host == host or origin_host.split(":")[0] == host.split(":")[0]:
            return  # Same-origin request

    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        referer_host = parsed.netloc
        if referer_host == host or referer_host.split(":")[0] == host.split(":")[0]:
            return  # Same-origin referer

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF validation failed",
    )


async def get_current_user(
    request: Request,
    header_token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request, header_token)
    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    # CSRF validation (only for cookie-based auth on mutating requests)
    _validate_csrf(request)

    user = await UserRepo(db).get_by_username(username)
    if user is None or not user.is_active:
        raise credentials_exception

    # Block all endpoints except password-change when must_change_password is set
    _PASSWORD_EXEMPT_PATHS = frozenset(
        {
            "/api/v1/auth/force-change-password",
            "/api/v1/auth/me",
            "/api/v1/auth/logout",
        }
    )
    if user.must_change_password and request.url.path not in _PASSWORD_EXEMPT_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
        )

    return user


def require_role(*roles: str) -> Callable:
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _check
