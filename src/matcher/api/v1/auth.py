from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user
from matcher.auth.security import create_access_token, hash_password, verify_password
from matcher.config import settings
from matcher.db.models import User
from matcher.db.repos.user import UserRepo
from matcher.schemas.user import (
    ForcePasswordChange,
    PasswordChange,
    ProfileUpdate,
    UserBrief,
)
from matcher.security.client_ip import get_client_ip
from matcher.security.rate_limit import login_rate_limiter

router = APIRouter(tags=["Auth"])

# Cookie name constants
ACCESS_TOKEN_COOKIE = "access_token"
CSRF_TOKEN_COOKIE = "csrf_token"


class LoginResponse(BaseModel):
    logged_in: bool = True
    must_change_password: bool = False


def _set_auth_cookies(response: JSONResponse, jwt_token: str) -> None:
    """Set the httpOnly JWT cookie and a non-httpOnly CSRF cookie."""
    csrf_token = secrets.token_hex(32)

    cookie_kwargs: dict = {
        "path": "/api",
        "httponly": True,
        "samesite": settings.cookie_samesite,
        "secure": settings.cookie_secure,
        "max_age": settings.jwt_expire_minutes * 60,
    }
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=jwt_token,
        **cookie_kwargs,
    )

    # CSRF cookie: readable by JS (not httpOnly), but scoped to same domain (SameSite=Lax)
    response.set_cookie(
        key=CSRF_TOKEN_COOKIE,
        value=csrf_token,
        path="/",
        httponly=False,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.jwt_expire_minutes * 60,
    )


def _clear_auth_cookies(response: JSONResponse) -> None:
    """Expire both auth cookies."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        path="/api",
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )
    response.delete_cookie(
        key=CSRF_TOKEN_COOKIE,
        path="/",
        httponly=False,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )


@router.post("/auth/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # Rate limiting by client IP
    client_ip = get_client_ip(request)
    redis = getattr(request.app.state, "arq_pool", None)
    if redis is not None:
        try:
            if await login_rate_limiter.is_blocked(redis, client_ip):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Please try again later.",
                )
        except HTTPException:
            raise
        except Exception:
            # Fail open on limiter outages to avoid auth lockout during Redis issues.
            pass

    user = await UserRepo(db).get_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        if redis is not None:
            try:
                await login_rate_limiter.record_attempt(redis, client_ip)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Successful login - reset rate limiter for this IP
    if redis is not None:
        try:
            await login_rate_limiter.reset(redis, client_ip)
        except Exception:
            pass

    token = create_access_token(data={"sub": user.username, "role": user.role})

    response = JSONResponse(
        content={"logged_in": True, "must_change_password": user.must_change_password}
    )
    _set_auth_cookies(response, token)
    return response


@router.post("/auth/logout")
async def logout():
    """Clear auth cookies."""
    response = JSONResponse(content={"logged_out": True})
    _clear_auth_cookies(response)
    return response


@router.get("/auth/me", response_model=UserBrief)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserBrief.model_validate(current_user)


@router.put("/auth/profile", response_model=UserBrief)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.full_name = body.full_name
    await db.commit()
    return UserBrief.model_validate(current_user)


@router.post("/auth/change-password")
async def change_password(
    body: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"ok": True}


@router.post("/auth/force-change-password")
async def force_change_password(
    body: ForcePasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not required",
        )
    current_user.hashed_password = hash_password(body.new_password)
    current_user.must_change_password = False
    await db.commit()

    # Re-issue JWT so the session reflects the updated state
    token = create_access_token(data={"sub": current_user.username, "role": current_user.role})
    response = JSONResponse(content={"ok": True})
    _set_auth_cookies(response, token)
    return response
