"""Tests for review API endpoints."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestReviewEndpoints:
    def _user(self) -> User:
        return User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=False,
        )

    @pytest.mark.asyncio
    async def test_review_requires_auth(self, async_client):
        resp = await async_client.post(
            "/api/v1/review/items/item_123",
            json={"final_decision": "accepted"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_review_item_not_found(self, async_client, auth_headers):
        mock_user = self._user()
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.get_item_with_request = AsyncMock(return_value=(None, None))
            resp = await async_client.post(
                "/api/v1/review/items/nonexistent",
                json={"final_decision": "accepted"},
                headers=auth_headers,
            )
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_review_invalid_decision(self, async_client, auth_headers):
        mock_user = self._user()
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/review/items/item_123",
                json={"final_decision": "invalid_value"},
                headers=auth_headers,
            )
            # Pydantic validation should reject invalid literal
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_review_conflict_when_reviewed_by_another_user(self, async_client, auth_headers):
        item = SimpleNamespace(final_decision="accepted", reviewed_by="other")
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_item_with_request = AsyncMock(return_value=(item, None))

            resp = await async_client.post(
                "/api/v1/review/items/item_123",
                json={"final_decision": "accepted"},
                headers=auth_headers,
            )

        assert resp.status_code == 409
        assert "already reviewed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_review_corrected_requires_existing_catalog_product(
        self, async_client, auth_headers, mock_db_session
    ):
        item = SimpleNamespace(final_decision=None, best_product_id=None, reviewed_by=None)
        mock_db_session.get = AsyncMock(return_value=None)

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_item_with_request = AsyncMock(return_value=(item, None))

            resp = await async_client.post(
                "/api/v1/review/items/item_123",
                json={"final_decision": "corrected", "final_product_id": "prod_missing"},
                headers=auth_headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Product not found in catalog"

    @pytest.mark.asyncio
    async def test_review_accepts_best_candidate_and_creates_alias_and_mapping(
        self, async_client, auth_headers, mock_db_session
    ):
        item = SimpleNamespace(
            final_decision=None,
            reviewed_by=None,
            best_product_id="prod_1",
            raw_text="Цемент 25 кг",
            normalized_text=None,
            confidence=Decimal("0.95"),
        )
        request = SimpleNamespace(supplier_id="sup_1")
        pipeline_context = SimpleNamespace(text="cement 25 kg")

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.review.AuditRepo") as MockAuditRepo,
            patch("matcher.api.v1.review.CatalogRepo") as MockCatalogRepo,
            patch("matcher.api.v1.review.SupplierRepo") as MockSupplierRepo,
            patch("matcher.api.v1.review.run_pipeline", return_value=pipeline_context),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            match_repo = MockMatchRepo.return_value
            match_repo.get_item_with_request = AsyncMock(return_value=(item, request))
            match_repo.update_item_review = AsyncMock()
            match_repo.create_golden_label = AsyncMock()
            audit = MockAuditRepo.return_value
            audit.log = AsyncMock()
            catalog_repo = MockCatalogRepo.return_value
            catalog_repo.create_alias = AsyncMock()
            supplier_repo = MockSupplierRepo.return_value
            supplier_repo.create_mapping = AsyncMock()

            resp = await async_client.post(
                "/api/v1/review/items/item_123",
                json={
                    "final_decision": "accepted",
                    "comment": "ok",
                    "create_alias": True,
                    "create_supplier_mapping": True,
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "request_item_id": "item_123"}
        match_repo.update_item_review.assert_awaited_once_with(
            request_item_id="item_123",
            decision="accepted",
            final_product_id="prod_1",
            reviewed_by="test_admin",
            review_notes="ok",
        )
        match_repo.create_golden_label.assert_awaited_once_with(
            raw_query="Цемент 25 кг",
            normalized_query="Цемент 25 кг",
            supplier_id="sup_1",
            product_id="prod_1",
            label_type="positive",
            source="review",
        )
        catalog_repo.create_alias.assert_awaited_once_with(
            product_id="prod_1",
            alias_text="Цемент 25 кг",
            normalized_text="cement 25 kg",
            alias_type="user_added",
            created_by="test_admin",
        )
        supplier_repo.create_mapping.assert_awaited_once()
        assert audit.log.await_count == 3
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_reject_creates_negative_label_without_request(
        self, async_client, auth_headers, mock_db_session
    ):
        item = SimpleNamespace(
            final_decision=None,
            reviewed_by=None,
            best_product_id="prod_1",
            raw_text="unknown",
            normalized_text="unknown norm",
            confidence=None,
        )
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.review.AuditRepo") as MockAuditRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            match_repo = MockMatchRepo.return_value
            match_repo.get_item_with_request = AsyncMock(return_value=(item, None))
            match_repo.update_item_review = AsyncMock()
            match_repo.create_golden_label = AsyncMock()
            MockAuditRepo.return_value.log = AsyncMock()

            resp = await async_client.post(
                "/api/v1/review/items/item_123",
                json={"final_decision": "rejected"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        match_repo.create_golden_label.assert_awaited_once_with(
            raw_query="unknown",
            normalized_query="unknown norm",
            supplier_id=None,
            product_id=None,
            label_type="negative",
            source="review",
        )
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_batch_review_skips_missing_items_and_missing_corrected_products(
        self, async_client, auth_headers, mock_db_session
    ):
        item = SimpleNamespace(
            raw_text="paint",
            normalized_text=None,
            best_product_id="prod_1",
            confidence=Decimal("0.8"),
        )
        request = SimpleNamespace(supplier_id="sup_1")
        mock_db_session.get = AsyncMock(return_value=None)

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.review.AuditRepo") as MockAuditRepo,
            patch("matcher.api.v1.review.CatalogRepo") as MockCatalogRepo,
            patch("matcher.api.v1.review.SupplierRepo") as MockSupplierRepo,
            patch("matcher.api.v1.review.run_pipeline", return_value=SimpleNamespace(text="paint")),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            match_repo = MockMatchRepo.return_value
            match_repo.get_item_with_request = AsyncMock(
                side_effect=[
                    (None, None),
                    (item, request),
                    (item, request),
                ]
            )
            match_repo.update_item_review = AsyncMock()
            match_repo.create_golden_label = AsyncMock()
            MockAuditRepo.return_value.log = AsyncMock()
            MockCatalogRepo.return_value.create_alias = AsyncMock()
            MockSupplierRepo.return_value.create_mapping = AsyncMock()

            resp = await async_client.post(
                "/api/v1/review/batch",
                json={
                    "items": [
                        {"request_item_id": "missing", "final_decision": "accepted"},
                        {
                            "request_item_id": "bad_product",
                            "final_decision": "corrected",
                            "final_product_id": "missing_product",
                        },
                        {
                            "request_item_id": "ok",
                            "final_decision": "accepted",
                            "create_alias": True,
                            "create_supplier_mapping": True,
                        },
                    ]
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "processed_count": 1}
        match_repo.update_item_review.assert_awaited_once()
        match_repo.create_golden_label.assert_awaited_once()
        MockCatalogRepo.return_value.create_alias.assert_awaited_once()
        MockSupplierRepo.return_value.create_mapping.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
