"""Tests for catalog API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from httpx import AsyncClient

from matcher.api.v1.catalog import upload_catalog_file
from matcher.config import settings
from matcher.db.models import CatalogProduct, IndexVersion, User


class TestCatalogEndpoints:
    @staticmethod
    def _admin_user() -> User:
        return User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )

    @pytest.mark.asyncio
    async def test_search_catalog_products_serializes_repo_items(self, async_client, auth_headers):
        product = CatalogProduct(
            product_id="p1",
            name="Подшипник SKF 6205",
            normalized_name="подшипник skf 6205",
            search_document="подшипник skf 6205",
            article="6205",
            brand="SKF",
            category_path="Bearings",
            is_active=True,
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.search_products = AsyncMock(return_value=[product])

            resp = await async_client.get(
                "/api/v1/catalog/products?q=6205&limit=10",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == [
            {
                "product_id": "p1",
                "name": "Подшипник SKF 6205",
                "article": "6205",
                "brand": "SKF",
                "category_path": "Bearings",
                "is_active": True,
            }
        ]
        MockCatalogRepo.return_value.search_products.assert_awaited_once_with(
            query="6205", limit=10
        )

    @pytest.mark.asyncio
    async def test_catalog_stats_reports_active_embedding_version(
        self, async_client, auth_headers, mock_db_session
    ):
        active_version = IndexVersion(
            index_version_id="idx_active",
            embedding_model="local-bge-m3",
            embedding_version="v1",
            lexical_version="lex-v1",
            rules_version="rules-v1",
            is_active=True,
            product_count=20,
            created_by="system",
        )
        inactive_version = IndexVersion(
            index_version_id="idx_old",
            embedding_model="old-model",
            embedding_version="v0",
            lexical_version="lex-v0",
            rules_version="rules-v0",
            is_active=False,
            product_count=10,
            created_by="system",
        )
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 15
        mock_db_session.execute.return_value = scalar_result

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
            patch("matcher.api.v1.settings._onec_settings") as mock_onec,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.count_active = AsyncMock(return_value=20)
            MockCatalogRepo.return_value.list_index_versions = AsyncMock(
                return_value=[inactive_version, active_version]
            )
            mock_onec.enabled = True
            mock_onec.base_url = "http://onec.local"

            resp = await async_client.get("/api/v1/catalog/stats", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == {
            "total_products": 20,
            "embedded_products": 15,
            "embedding_model": "local-bge-m3",
            "embedding_coverage_pct": 75.0,
            "onec_connected": True,
        }

    @pytest.mark.asyncio
    async def test_catalog_stats_handles_empty_catalog(
        self, async_client, auth_headers, mock_db_session
    ):
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = None
        mock_db_session.execute.return_value = scalar_result

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
            patch("matcher.api.v1.settings._onec_settings") as mock_onec,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.count_active = AsyncMock(return_value=0)
            MockCatalogRepo.return_value.list_index_versions = AsyncMock(return_value=[])
            mock_onec.enabled = False
            mock_onec.base_url = None

            resp = await async_client.get("/api/v1/catalog/stats", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["embedding_coverage_pct"] == 0.0
        assert resp.json()["embedding_model"] is None
        assert resp.json()["onec_connected"] is False

    @pytest.mark.asyncio
    async def test_import_requires_auth(self, async_client):
        resp = await async_client.post(
            "/api/v1/catalog/import",
            json={"source_type": "csv"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_import_requires_operator_role(self, async_client, viewer_headers):
        mock_user = User(
            user_id="u1",
            username="test_viewer",
            hashed_password="x",
            role="viewer",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/import",
                json={"source_type": "csv", "file_url": "http://example.com/file.csv"},
                headers=viewer_headers,
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_import_accepted(self, async_client, auth_headers):
        mock_user = self._admin_user()
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/import",
                json={"source_type": "csv", "file_url": "http://example.com/file.csv"},
                headers=auth_headers,
            )
            assert resp.status_code == 202
            data = resp.json()
            assert data["status"] == "queued"
            assert "job_id" in data

    @pytest.mark.asyncio
    async def test_reindex_requires_admin(self, async_client, operator_headers):
        mock_user = User(
            user_id="u1",
            username="test_operator",
            hashed_password="x",
            role="operator",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/reindex",
                json={},
                headers=operator_headers,
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reindex_returns_202(self, async_client, auth_headers):
        mock_user = self._admin_user()
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/reindex",
                json={},
                headers=auth_headers,
            )
            assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_catalog_upload_uses_shared_upload_dir(
        self, async_client: AsyncClient, auth_headers, tmp_path: Path, mock_arq_pool
    ):
        mock_user = self._admin_user()
        original_dir = settings.catalog_upload_dir

        try:
            settings.catalog_upload_dir = str(tmp_path)
            with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
                MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
                resp = await async_client.post(
                    "/api/v1/catalog/upload",
                    files={"file": ("catalog.csv", BytesIO(b"name\nitem\n"), "text/csv")},
                    headers=auth_headers,
                )
        finally:
            settings.catalog_upload_dir = original_dir

        assert resp.status_code == 202
        kwargs = mock_arq_pool.enqueue_job.await_args.kwargs
        assert kwargs["_queue_name"] == "catalog"
        assert kwargs["_job_id"].startswith("job_")
        assert kwargs["file_path"].startswith(str(tmp_path))
        assert Path(kwargs["file_path"]).exists()

    @pytest.mark.asyncio
    async def test_upload_catalog_file_rejects_missing_filename(
        self, mock_db_session, mock_arq_pool
    ):
        file = UploadFile(file=BytesIO(b"name\nitem\n"), filename="")

        with pytest.raises(HTTPException) as exc_info:
            await upload_catalog_file(
                file=file,
                arq_pool=mock_arq_pool,
                db=mock_db_session,
                current_user=self._admin_user(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "No filename provided"

    @pytest.mark.asyncio
    async def test_upload_catalog_file_rejects_unsupported_extension(
        self, async_client, auth_headers
    ):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            resp = await async_client.post(
                "/api/v1/catalog/upload",
                files={"file": ("catalog.txt", BytesIO(b"name\nitem\n"), "text/plain")},
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Only .csv and .xlsx files are supported"

    @pytest.mark.asyncio
    async def test_upload_catalog_file_rejects_too_large_file(self, async_client, auth_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            resp = await async_client.post(
                "/api/v1/catalog/upload",
                files={"file": ("catalog.csv", BytesIO(b"x" * (50 * 1024 * 1024 + 1)), "text/csv")},
                headers=auth_headers,
            )

        assert resp.status_code == 413
        assert resp.json()["detail"] == "File too large. Max size is 50 MB"

    @pytest.mark.asyncio
    async def test_upload_catalog_file_rejects_xlsx_with_wrong_magic(
        self, async_client, auth_headers
    ):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            resp = await async_client.post(
                "/api/v1/catalog/upload",
                files={
                    "file": (
                        "catalog.xlsx",
                        BytesIO(b"not-a-zip-workbook"),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "File content does not match .xlsx format."

    @pytest.mark.asyncio
    async def test_upload_catalog_file_removes_temp_file_when_enqueue_fails(
        self, async_client, auth_headers, tmp_path: Path
    ):
        original_dir = settings.catalog_upload_dir
        try:
            settings.catalog_upload_dir = str(tmp_path)
            with (
                patch("matcher.auth.deps.UserRepo") as MockUserRepo,
                patch(
                    "matcher.api.v1.catalog.enqueue_unique_job", new_callable=AsyncMock
                ) as enqueue,
            ):
                MockUserRepo.return_value.get_by_username = AsyncMock(
                    return_value=self._admin_user()
                )
                enqueue.side_effect = RuntimeError("redis down")
                with pytest.raises(RuntimeError, match="redis down"):
                    await async_client.post(
                        "/api/v1/catalog/upload",
                        files={"file": ("catalog.csv", BytesIO(b"name\nitem\n"), "text/csv")},
                        headers=auth_headers,
                    )
        finally:
            settings.catalog_upload_dir = original_dir

        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_list_index_versions_serializes_dates(self, async_client, auth_headers):
        version = IndexVersion(
            index_version_id="idx_1",
            embedding_model="local-bge-m3",
            embedding_version="v1",
            lexical_version="lex-v1",
            rules_version="rules-v1",
            is_active=True,
            product_count=42,
            created_by="admin",
            created_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
            activated_at=datetime(2026, 5, 31, 12, 5, tzinfo=UTC),
        )
        version_without_dates = IndexVersion(
            index_version_id="idx_2",
            embedding_model="local-bge-m3",
            embedding_version="v0",
            lexical_version="lex-v0",
            rules_version="rules-v0",
            is_active=False,
            product_count=0,
            created_by=None,
            created_at=None,
            activated_at=None,
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.list_index_versions = AsyncMock(
                return_value=[version, version_without_dates]
            )
            resp = await async_client.get("/api/v1/catalog/index-versions", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["items"] == [
            {
                "index_version_id": "idx_1",
                "embedding_model": "local-bge-m3",
                "embedding_version": "v1",
                "is_active": True,
                "product_count": 42,
                "created_by": "admin",
                "created_at": "2026-05-31T12:00:00+00:00",
                "activated_at": "2026-05-31T12:05:00+00:00",
            },
            {
                "index_version_id": "idx_2",
                "embedding_model": "local-bge-m3",
                "embedding_version": "v0",
                "is_active": False,
                "product_count": 0,
                "created_by": None,
                "created_at": None,
                "activated_at": None,
            },
        ]

    @pytest.mark.asyncio
    async def test_rollback_index_activates_version(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.activate_index_version = AsyncMock(return_value=True)
            resp = await async_client.post(
                "/api/v1/catalog/rollback",
                json={"index_version_id": "idx_1"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "activated_version": "idx_1"}
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_index_returns_404_for_missing_version(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.activate_index_version = AsyncMock(return_value=False)
            resp = await async_client.post(
                "/api/v1/catalog/rollback",
                json={"index_version_id": "idx_missing"},
                headers=auth_headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Index version not found"
        mock_db_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_catalog_product_deletes_existing_product(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.delete_product = AsyncMock(return_value=True)
            resp = await async_client.delete("/api/v1/catalog/products/p1", headers=auth_headers)

        assert resp.status_code == 204
        MockCatalogRepo.return_value.delete_product.assert_awaited_once_with("p1")
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_catalog_product_returns_404_for_missing_product(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.catalog.CatalogRepo") as MockCatalogRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._admin_user())
            MockCatalogRepo.return_value.delete_product = AsyncMock(return_value=False)
            resp = await async_client.delete(
                "/api/v1/catalog/products/missing", headers=auth_headers
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Product not found"
        mock_db_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_all_catalog_products_gone(self, async_client, auth_headers):
        mock_user = self._admin_user()
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.delete("/api/v1/catalog/products", headers=auth_headers)
        assert resp.status_code == 410
