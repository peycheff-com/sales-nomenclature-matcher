"""Tests for suppliers API endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestSuppliersEndpoints:
    def _user(self, role: str = "admin") -> User:
        return User(
            user_id="u1",
            username=f"test_{role}",
            hashed_password="x",
            role=role,
            is_active=True,
            must_change_password=False,
        )

    def _supplier(self, supplier_id: str = "sup_1"):
        return SimpleNamespace(
            supplier_id=supplier_id,
            supplier_name="Supplier One",
            strict_mode=True,
            is_active=True,
        )

    def _mapping(self, mapping_id: str = "map_1"):
        return SimpleNamespace(
            mapping_id=mapping_id,
            supplier_id="sup_1",
            supplier_sku="SKU-1",
            supplier_article="ART-1",
            supplier_raw_text="Цемент",
            product_id="prod_1",
            mapping_type="approved",
            confidence=0.9,
        )

    @pytest.mark.asyncio
    async def test_list_suppliers_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/suppliers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_suppliers(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.list_suppliers = AsyncMock(return_value=[self._supplier()])
            resp = await async_client.get("/api/v1/suppliers", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["items"][0]["supplier_id"] == "sup_1"
            MockRepo.return_value.list_suppliers.assert_awaited_once_with(active_only=False)

    @pytest.mark.asyncio
    async def test_create_mapping_requires_operator(self, async_client, viewer_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user("viewer"))
            resp = await async_client.post(
                "/api/v1/suppliers/s1/mappings",
                json={"product_id": "p1", "mapping_type": "approved"},
                headers=viewer_headers,
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_supplier_conflict_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            repo = MockRepo.return_value
            repo.get_supplier = AsyncMock(return_value=self._supplier())

            conflict = await async_client.post(
                "/api/v1/suppliers",
                json={"supplier_id": "sup_1", "supplier_name": "Supplier One"},
                headers=auth_headers,
            )

        assert conflict.status_code == 400
        assert conflict.json()["detail"] == "Supplier with this ID already exists"

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            repo = MockRepo.return_value
            repo.get_supplier = AsyncMock(return_value=None)
            repo.create_supplier = AsyncMock(return_value=self._supplier())

            created = await async_client.post(
                "/api/v1/suppliers",
                json={
                    "supplier_id": "sup_1",
                    "supplier_name": "Supplier One",
                    "strict_mode": True,
                },
                headers=auth_headers,
            )

        assert created.status_code == 201
        assert created.json()["strict_mode"] is True
        repo.create_supplier.assert_awaited_once_with(
            supplier_id="sup_1",
            name="Supplier One",
            strict_mode=True,
        )
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_supplier_not_found_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.update_supplier = AsyncMock(return_value=None)

            missing = await async_client.put(
                "/api/v1/suppliers/missing",
                json={"supplier_name": "Missing"},
                headers=auth_headers,
            )

        assert missing.status_code == 404

        updated_supplier = self._supplier()
        updated_supplier.supplier_name = "Updated"
        updated_supplier.is_active = False
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.update_supplier = AsyncMock(return_value=updated_supplier)

            updated = await async_client.put(
                "/api/v1/suppliers/sup_1",
                json={"supplier_name": "Updated", "is_active": False},
                headers=auth_headers,
            )

        assert updated.status_code == 200
        assert updated.json()["supplier_name"] == "Updated"
        MockRepo.return_value.update_supplier.assert_awaited_once_with(
            supplier_id="sup_1",
            supplier_name="Updated",
            is_active=False,
        )
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_supplier_mapping_not_found_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_supplier = AsyncMock(return_value=None)

            missing = await async_client.post(
                "/api/v1/suppliers/missing/mappings",
                json={"product_id": "prod_1"},
                headers=auth_headers,
            )

        assert missing.status_code == 404

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockSupplierRepo,
            patch("matcher.api.v1.suppliers.AuditRepo") as MockAuditRepo,
            patch(
                "matcher.api.v1.suppliers.run_pipeline",
                return_value=SimpleNamespace(text="cement"),
            ),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            repo = MockSupplierRepo.return_value
            repo.get_supplier = AsyncMock(return_value=self._supplier())
            repo.create_mapping = AsyncMock(return_value=self._mapping())
            MockAuditRepo.return_value.log = AsyncMock()

            created = await async_client.post(
                "/api/v1/suppliers/sup_1/mappings",
                json={
                    "supplier_sku": "SKU-1",
                    "supplier_article": "ART-1",
                    "supplier_raw_text": "Цемент",
                    "product_id": "prod_1",
                    "mapping_type": "approved",
                    "confidence": 0.9,
                },
                headers=auth_headers,
            )

        assert created.status_code == 201
        assert created.json()["mapping_id"] == "map_1"
        repo.create_mapping.assert_awaited_once()
        assert repo.create_mapping.await_args.kwargs["data"]["normalized_supplier_text"] == "cement"
        MockAuditRepo.return_value.log.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_supplier_not_found_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.delete_supplier = AsyncMock(return_value=False)

            missing = await async_client.delete("/api/v1/suppliers/missing", headers=auth_headers)

        assert missing.status_code == 404

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.delete_supplier = AsyncMock(return_value=True)

            deleted = await async_client.delete("/api/v1/suppliers/sup_1", headers=auth_headers)

        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_supplier_mappings_not_found_and_success(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_supplier = AsyncMock(return_value=None)

            missing = await async_client.get(
                "/api/v1/suppliers/missing/mappings",
                headers=auth_headers,
            )

        assert missing.status_code == 404

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            repo = MockRepo.return_value
            repo.get_supplier = AsyncMock(return_value=self._supplier())
            repo.get_supplier_mappings = AsyncMock(return_value=[self._mapping()])

            listed = await async_client.get(
                "/api/v1/suppliers/sup_1/mappings?limit=10&offset=5",
                headers=auth_headers,
            )

        assert listed.status_code == 200
        assert listed.json()["items"][0]["mapping_id"] == "map_1"
        repo.get_supplier_mappings.assert_awaited_once_with("sup_1", limit=10, offset=5)
