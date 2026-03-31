import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_catalog_import_rejects_concurrent():
    from matcher.worker.tasks import catalog_import

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=False)  # NX fails = lock held
    ctx = {"db_factory": AsyncMock(), "redis": mock_redis}
    result = await catalog_import(ctx, "job_2", "csv", file_url="http://example.com/f.csv")
    assert result["status"] == "failed"
    assert "already running" in result["error"].lower()


@pytest.mark.asyncio
async def test_catalog_import_acquires_and_releases_lock():
    from matcher.worker.tasks import catalog_import

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)  # NX succeeds = lock acquired
    ctx = {"db_factory": AsyncMock(), "redis": mock_redis}
    # source_type is invalid on purpose so we get a quick failure after lock
    result = await catalog_import(ctx, "job_3", "unsupported")
    assert result["status"] == "failed"
    # Lock should have been released
    mock_redis.delete.assert_called_once_with("lock:catalog_import")


@pytest.mark.asyncio
async def test_catalog_import_releases_lock_on_exception():
    from matcher.worker.tasks import catalog_import

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    ctx = {"db_factory": AsyncMock(), "redis": mock_redis}
    # csv with no file_url/file_path should fail but still release lock
    result = await catalog_import(ctx, "job_4", "csv")
    assert result["status"] == "failed"
    mock_redis.delete.assert_called_once_with("lock:catalog_import")


@pytest.mark.asyncio
async def test_catalog_import_works_without_redis():
    from matcher.worker.tasks import catalog_import

    # No redis in context — should proceed without locking
    ctx = {"db_factory": AsyncMock()}
    result = await catalog_import(ctx, "job_5", "unsupported")
    assert result["status"] == "failed"
    assert "unsupported" in result["error"].lower()
