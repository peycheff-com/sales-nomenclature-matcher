from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Response schemas ---


class UserOut(BaseModel):
    """Full user detail returned by admin endpoints."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str
    full_name: str | None
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime


class UserBrief(BaseModel):
    """Lightweight user info returned by /auth/me."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str
    full_name: str | None
    role: str
    must_change_password: bool


# --- Admin input schemas ---


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str | None = Field(None, max_length=200)
    role: Literal["admin", "operator", "viewer"] = "operator"
    password: str = Field(..., min_length=6, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    role: Literal["admin", "operator", "viewer"] | None = None
    is_active: bool | None = None


class UserResetPassword(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


# --- Self-service input schemas ---


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class ForcePasswordChange(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)
