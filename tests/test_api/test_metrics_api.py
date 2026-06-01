"""Tests for metrics API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestMetricsEndpoints:
    @pytest.mark.asyncio
    async def test_metrics_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/metrics/quality")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_quality_metrics_empty(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        empty_metrics = {
            "total_cases": 0,
            "top1_accuracy": None,
            "top3_recall": None,
            "precision_at_1": None,
            "auto_match_false_positive_rate": None,
            "review_acceptance_rate": None,
            "avg_latency_ms": None,
        }
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.metrics.MetricsRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.compute_quality_metrics = AsyncMock(return_value=empty_metrics)
            resp = await async_client.get("/api/v1/metrics/quality", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_cases"] == 0
            assert data["top1_accuracy"] is None

    @pytest.mark.asyncio
    async def test_quality_metrics_with_data(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        metrics = {
            "total_cases": 150,
            "top1_accuracy": 0.92,
            "top3_recall": 0.97,
            "precision_at_1": 0.91,
            "auto_match_false_positive_rate": 0.03,
            "review_acceptance_rate": 0.85,
            "avg_latency_ms": 245.0,
        }
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.metrics.MetricsRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.compute_quality_metrics = AsyncMock(return_value=metrics)
            resp = await async_client.get("/api/v1/metrics/quality", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_cases"] == 150
            assert data["top1_accuracy"] == 0.92

    @pytest.mark.asyncio
    async def test_quality_metrics_passes_supplier_and_category_filters(
        self, async_client, auth_headers
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        metrics = {
            "total_cases": 2,
            "top1_accuracy": 0.5,
            "top3_recall": None,
            "precision_at_1": 0.5,
            "auto_match_false_positive_rate": 0.5,
            "review_acceptance_rate": 0.5,
            "avg_latency_ms": 100.0,
        }
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.metrics.MetricsRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.compute_quality_metrics = AsyncMock(return_value=metrics)

            resp = await async_client.get(
                "/api/v1/metrics/quality",
                params={"supplier_id": "sup_1", "category_id": "cat_1"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        MockRepo.return_value.compute_quality_metrics.assert_awaited_once_with(
            supplier_id="sup_1",
            category_id="cat_1",
        )

    @pytest.mark.asyncio
    async def test_token_usage_summary(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        summary = {
            "period_days": 7,
            "totals": {"total_tokens": 100},
            "by_provider": [],
            "by_model": [],
            "daily": [],
        }
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.metrics.TokenUsageRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.get_summary = AsyncMock(return_value=summary)

            resp = await async_client.get(
                "/api/v1/metrics/tokens",
                params={"days": 7, "provider": "local"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == summary
        MockRepo.return_value.get_summary.assert_awaited_once_with(days=7, provider="local")

    @pytest.mark.asyncio
    async def test_quality_history_serializes_reports(
        self, async_client, auth_headers, mock_db_session
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        report = SimpleNamespace(
            report_id="report_1",
            index_version_id="idx_1",
            top1_accuracy=Decimal("0.90"),
            top3_recall=Decimal("0.95"),
            precision_at_1=Decimal("0.80"),
            auto_match_fp_rate=Decimal("0.10"),
            review_acceptance_rate=Decimal("0.70"),
            total_cases=42,
            created_at=datetime(2026, 5, 31, 12, 30, tzinfo=UTC),
        )
        result = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [report])
        )
        mock_db_session.execute = AsyncMock(return_value=result)

        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.get(
                "/api/v1/metrics/quality/history",
                params={"supplier_id": "sup_1", "days": 14},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "items": [
                {
                    "report_id": "report_1",
                    "index_version_id": "idx_1",
                    "top1_accuracy": 0.9,
                    "top3_recall": 0.95,
                    "precision_at_1": 0.8,
                    "auto_match_fp_rate": 0.1,
                    "review_acceptance_rate": 0.7,
                    "total_cases": 42,
                    "created_at": "2026-05-31T12:30:00+00:00",
                }
            ]
        }
        mock_db_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_quality_history_category_and_all_scope_paths(
        self, async_client, auth_headers, mock_db_session
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        empty_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
        mock_db_session.execute = AsyncMock(return_value=empty_result)

        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            category_resp = await async_client.get(
                "/api/v1/metrics/quality/history",
                params={"category_id": "cat_1"},
                headers=auth_headers,
            )
            all_resp = await async_client.get(
                "/api/v1/metrics/quality/history",
                headers=auth_headers,
            )

        assert category_resp.status_code == 200
        assert category_resp.json() == {"items": []}
        assert all_resp.status_code == 200
        assert all_resp.json() == {"items": []}
        assert mock_db_session.execute.await_count == 2
