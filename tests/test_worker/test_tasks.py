"""Tests for worker tasks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matcher.worker.tasks import batch_match, catalog_import


class TestBatchMatch:
    @pytest.mark.asyncio
    async def test_request_not_found(self):
        mock_session = AsyncMock()

        # Create an async context manager mock for db_factory()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        with patch("matcher.db.repos.match.MatchRepo") as MockRepo:
            MockRepo.return_value.get_request = AsyncMock(return_value=None)
            result = await batch_match({"db_factory": mock_factory}, "req_nonexistent")
            assert result["status"] == "failed"
            assert result["error"] == "not found"


class TestCatalogImport:
    @pytest.mark.asyncio
    async def test_unsupported_source_type(self):
        result = await catalog_import(
            {"db_factory": MagicMock()},
            "job_1",
            source_type="odata",
        )
        assert result["status"] == "failed"
        assert "Unsupported" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_missing_file_url(self):
        result = await catalog_import(
            {"db_factory": MagicMock()},
            "job_2",
            source_type="csv",
        )
        assert result["status"] == "failed"
        assert "file_url" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_csv_import_supported(self):
        """Verify that csv source_type passes the type check (fails on download, which is expected)."""
        result = await catalog_import(
            {"db_factory": MagicMock()},
            "job_3",
            source_type="csv",
            file_url="http://nonexistent.example.com/test.csv",
        )
        # Should fail on download, not on source_type validation
        assert result["status"] == "failed"
        assert "Unsupported" not in result.get("error", "")
