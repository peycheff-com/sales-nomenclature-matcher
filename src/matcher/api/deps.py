from __future__ import annotations

from collections.abc import AsyncGenerator

from arq import ArqRedis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.engine import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool
