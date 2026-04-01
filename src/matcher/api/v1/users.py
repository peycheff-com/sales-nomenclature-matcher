from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import require_role
from matcher.auth.security import hash_password
from matcher.db.models import User
from matcher.db.repos.user import UserRepo
from matcher.schemas.user import (
    UserCreate,
    UserOut,
    UserResetPassword,
    UserUpdate,
)

router = APIRouter(tags=["Users"])


@router.get("/users", response_model=dict)
async def list_users(
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    users = await UserRepo(db).list_users()
    return {"items": [UserOut.model_validate(u) for u in users]}


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepo(db)
    existing = await repo.get_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    user = await repo.create_user(
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        must_change_password=True,
    )
    await db.commit()
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepo(db).get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Prevent admin from deactivating or demoting themselves
    if user_id == admin.user_id:
        if body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account",
            )
        if body.role is not None and body.role != admin.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own role",
            )

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    user = await UserRepo(db).update_user(user_id, **updates)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.commit()
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    body: UserResetPassword,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = True
    await db.commit()
    return {"ok": True}
