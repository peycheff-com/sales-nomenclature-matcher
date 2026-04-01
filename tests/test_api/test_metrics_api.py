"""Tests for metrics API endpoints."""

from __future__ import annotations

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
