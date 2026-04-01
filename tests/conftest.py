from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from matcher.api.deps import get_arq_pool, get_db
from matcher.auth.security import create_access_token
from matcher.config import settings
from matcher.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Check if DB is available
_db_available = False
try:
    import asyncio as _aio

    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine as _cae

    _eng = _cae(settings.async_database_url, echo=False)

    async def _check():
        async with _eng.connect() as conn:
            result = await conn.execute(_text("SELECT count(*) FROM catalog_products"))
            return (result.scalar() or 0) > 0

    _db_available = _aio.run(_check())
    _aio.run(_eng.dispose())
except Exception:
    _db_available = False

db_required = pytest.mark.skipif(not _db_available, reason="Database not available or empty")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.async_database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_db_session():
    """Mock async DB session for unit tests."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_arq_pool():
    """Mock ARQ Redis pool for unit tests."""
    pool = MagicMock()
    pool.enqueue_job = AsyncMock()
    return pool


@pytest_asyncio.fixture
async def async_client(mock_db_session, mock_arq_pool):
    """Async test client with ASGITransport and dependency overrides."""

    async def _override_get_db():
        yield mock_db_session

    async def _override_get_arq_pool():
        return mock_arq_pool

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_pool] = _override_get_arq_pool

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_token() -> str:
    """Create a valid JWT token for testing."""
    return create_access_token(data={"sub": "test_admin", "role": "admin"})


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def operator_token() -> str:
    return create_access_token(data={"sub": "test_operator", "role": "operator"})


@pytest.fixture
def operator_headers(operator_token: str) -> dict:
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def viewer_token() -> str:
    return create_access_token(data={"sub": "test_viewer", "role": "viewer"})


@pytest.fixture
def viewer_headers(viewer_token: str) -> dict:
    return {"Authorization": f"Bearer {viewer_token}"}
