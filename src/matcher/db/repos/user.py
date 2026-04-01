from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import User


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_users(self) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.username)
        )
        return list(result.scalars().all())

    async def create_user(
        self,
        username: str,
        hashed_password: str,
        full_name: str | None = None,
        role: str = "operator",
        must_change_password: bool = True,
    ) -> User:
        user = User(
            user_id=f"usr_{uuid.uuid4().hex[:12]}",
            username=username,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            must_change_password=must_change_password,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_user(self, user_id: str, **kwargs: object) -> User | None:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        for k, v in kwargs.items():
            if hasattr(user, k):
                setattr(user, k, v)
        await self.session.flush()
        return user
