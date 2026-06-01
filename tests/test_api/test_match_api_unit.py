from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from matcher.db.models import MatchRequest, MatchRequestItem, User


def _admin_user() -> User:
    return User(
        user_id="u1",
        username="test_admin",
        hashed_password="x",
        role="admin",
        is_active=True,
    )


def _match_request(status: str = "done") -> MatchRequest:
    return MatchRequest(
        request_id="req_1",
        supplier_id="sup_1",
        source_type="api",
        submitted_by="test_admin",
        file_name="input.xlsx",
        job_name="batch_match",
        job_payload_json={"retry": True},
        status=status,
        total_items=2,
        processed_items=1,
        auto_matched_items=1,
        review_needed_items=0,
        no_match_items=0,
        error_message=None,
        created_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 5, 31, 12, 1, tzinfo=UTC),
        finished_at=datetime(2026, 5, 31, 12, 2, tzinfo=UTC),
    )


def _match_item() -> MatchRequestItem:
    return MatchRequestItem(
        request_item_id="item_1",
        request_id="req_1",
        line_id="1",
        raw_text="SKF 6205",
        original_row_json={"Номенклатура": "SKF 6205"},
        normalized_text="skf 6205",
        extracted_attributes={"brand": "SKF"},
        status="review_needed",
        confidence=Decimal("0.82"),
        best_product_id="p1",
        reasons_json=["needs review"],
    )


class _FakeAsyncClient:
    response: object | None = None
    error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url: str):
        if self.error:
            raise self.error
        assert "docs.google.com/spreadsheets" in url
        return self.response


def _http_response(status_code: int = 200, text: str = "name\nSKF 6205\n", url: str = "x"):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.url = url
    response.raise_for_status = MagicMock()
    return response


class TestMatchApiUnit:
    @pytest.mark.asyncio
    async def test_match_sync_persists_and_counts_results(
        self, async_client, auth_headers, mock_db_session
    ):
        auto_result = SimpleNamespace(
            request_item_id="item_1",
            line_id="1",
            raw_text="SKF 6205",
            normalized_text="skf 6205",
            extracted_attributes={"brand": "SKF"},
            status="auto_match",
            confidence=0.98,
            best_candidate={
                "product_id": "p1",
                "name": "Bearing SKF 6205",
                "article": "6205",
                "brand": "SKF",
                "category_path": "Bearings",
            },
            alternatives=[
                {
                    "product_id": "p2",
                    "name": "Bearing 6205",
                    "retrieval_rank": 2,
                    "final_score": 0.81,
                    "reasons": ["fallback"],
                }
            ],
            reasons=["exact article"],
        )
        review_result = SimpleNamespace(
            request_item_id="item_2",
            line_id="2",
            raw_text="SKF",
            normalized_text="skf",
            extracted_attributes={},
            status="review_needed",
            confidence=0.8,
            best_candidate=None,
            alternatives=[],
            reasons=["ambiguous"],
        )
        no_match_result = SimpleNamespace(
            request_item_id="item_3",
            line_id="3",
            raw_text="Unknown item",
            normalized_text="unknown item",
            extracted_attributes={},
            status="no_match",
            confidence=0.2,
            best_candidate=None,
            alternatives=[],
            reasons=["no candidates"],
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch(
                "matcher.api.v1.settings.load_persisted_settings", new_callable=AsyncMock
            ) as load,
            patch("matcher.api.v1.match.match_single", new_callable=AsyncMock) as match_single,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            match_single.side_effect = [auto_result, review_result, no_match_result]
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.update_request_status = AsyncMock()

            resp = await async_client.post(
                "/api/v1/match",
                json={
                    "supplier_id": "sup_1",
                    "items": [
                        {
                            "line_id": "1",
                            "raw_text": "SKF 6205",
                            "original_row": {"Номенклатура": "SKF 6205"},
                        },
                        {"line_id": "2", "raw_text": "SKF"},
                        {"line_id": "3", "raw_text": "Unknown item"},
                    ],
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["best_candidate"]["product_id"] == "p1"
        assert result["alternatives"][0]["product_id"] == "p2"
        assert result["original_row"] == {"Номенклатура": "SKF 6205"}
        load.assert_awaited_once_with(mock_db_session, force=True)
        MockMatchRepo.return_value.update_request_status.assert_awaited_once()
        update_kwargs = MockMatchRepo.return_value.update_request_status.await_args.kwargs
        assert update_kwargs["auto_matched_items"] == 1
        assert update_kwargs["review_needed_items"] == 1
        assert update_kwargs["no_match_items"] == 1
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_match_batch_stores_items_and_enqueues(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.match.enqueue_request_job", new_callable=AsyncMock) as enqueue,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.create_items = AsyncMock()
            resp = await async_client.post(
                "/api/v1/match/batch",
                json={"items": [{"line_id": "1", "raw_text": "SKF 6205"}]},
                headers=auth_headers,
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        MockMatchRepo.return_value.create_request.assert_awaited_once()
        MockMatchRepo.return_value.create_items.assert_awaited_once()
        enqueue.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preview_google_sheet_success_and_error_branches(
        self, async_client, auth_headers
    ):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview?url=https://example.com/not-sheet",
                headers=auth_headers,
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid Google Sheets URL"

        doc_id = "a" * 201
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                f"/api/v1/match/google-sheet/preview?url=https://docs.google.com/spreadsheets/d/{doc_id}",
                headers=auth_headers,
            )
        assert resp.status_code == 400

        _FakeAsyncClient.response = _http_response(text="name\nSKF 6205\n")
        _FakeAsyncClient.error = None
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.httpx.AsyncClient", _FakeAsyncClient),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview"
                "?url=https://docs.google.com/spreadsheets/d/abc123/edit?gid=99",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json() == {"rows": [{"name": "SKF 6205"}]}

        _FakeAsyncClient.response = _http_response(status_code=404)
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.httpx.AsyncClient", _FakeAsyncClient),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview"
                "?url=https://docs.google.com/spreadsheets/d/abc123/edit",
                headers=auth_headers,
            )
        assert resp.status_code == 404

        _FakeAsyncClient.response = _http_response(url="https://accounts.google.com/ServiceLogin")
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.httpx.AsyncClient", _FakeAsyncClient),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview"
                "?url=https://docs.google.com/spreadsheets/d/abc123/edit",
                headers=auth_headers,
            )
        assert resp.status_code == 403

        _FakeAsyncClient.response = _http_response(text="")
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.httpx.AsyncClient", _FakeAsyncClient),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview"
                "?url=https://docs.google.com/spreadsheets/d/abc123/edit",
                headers=auth_headers,
            )
        assert resp.status_code == 400

        _FakeAsyncClient.response = None
        _FakeAsyncClient.error = httpx.RequestError("network")
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.httpx.AsyncClient", _FakeAsyncClient),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.get(
                "/api/v1/match/google-sheet/preview"
                "?url=https://docs.google.com/spreadsheets/d/abc123/edit",
                headers=auth_headers,
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_list_and_get_match_requests(self, async_client, auth_headers):
        request = _match_request()
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.list_requests = AsyncMock(return_value=([request], 1))
            resp = await async_client.get(
                "/api/v1/match/requests?page=2&limit=10&status=done&supplier_id=sup_1"
                "&created_after=2026-05-31T00:00:00%2B00:00",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        MockMatchRepo.return_value.list_requests.assert_awaited_once()

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request = AsyncMock(return_value=request)
            resp = await async_client.get("/api/v1/match/requests/req_1", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["request_id"] == "req_1"

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request = AsyncMock(return_value=None)
            resp = await async_client.get("/api/v1/match/requests/missing", headers=auth_headers)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_match_items_candidates_and_review_queue(self, async_client, auth_headers):
        item = _match_item()
        candidates = [{"product_id": "p1", "name": "Bearing SKF 6205", "final_score": 0.82}]

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request_items = AsyncMock(return_value=([item], 1))
            resp = await async_client.get(
                "/api/v1/match/requests/req_1/items?status=review_needed&page=2&page_size=10",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["items"][0]["confidence"] == 0.82
        assert resp.json()["items"][0]["reasons"] == ["needs review"]

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_item_candidates = AsyncMock(return_value=candidates)
            resp = await async_client.get(
                "/api/v1/match/items/item_1/candidates", headers=auth_headers
            )

        assert resp.status_code == 200
        assert resp.json() == {"request_item_id": "item_1", "candidates": candidates}

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_review_queue = AsyncMock(
                return_value=([(item, "sup_1", "input.xlsx")], 1)
            )
            resp = await async_client.get(
                "/api/v1/match/review-queue?supplier_id=sup_1&page=2&page_size=10",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["items"][0]["supplier_id"] == "sup_1"

    @pytest.mark.asyncio
    async def test_retry_match_request_branches(
        self, async_client, auth_headers, mock_db_session
    ):
        retryable = _match_request(status="failed")
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.match.enqueue_request_job", new_callable=AsyncMock) as enqueue,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request = AsyncMock(return_value=retryable)
            MockMatchRepo.return_value.update_request_status = AsyncMock()
            MockMatchRepo.return_value.clear_item_results = AsyncMock()
            resp = await async_client.post(
                "/api/v1/match/requests/req_1/retry", headers=auth_headers
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "request_id": "req_1", "status": "queued"}
        MockMatchRepo.return_value.clear_item_results.assert_awaited_once_with("req_1")
        enqueue.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request = AsyncMock(return_value=None)
            resp = await async_client.post(
                "/api/v1/match/requests/missing/retry", headers=auth_headers
            )
        assert resp.status_code == 404

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.get_request = AsyncMock(return_value=_match_request())
            resp = await async_client.post(
                "/api/v1/match/requests/req_1/retry", headers=auth_headers
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_match_request_branches(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.delete_request = AsyncMock(return_value=True)
            resp = await async_client.delete("/api/v1/match/requests/req_1", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "request_id": "req_1"}
        mock_db_session.commit.assert_awaited_once()

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.match.MatchRepo") as MockMatchRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            MockMatchRepo.return_value.delete_request = AsyncMock(return_value=False)
            resp = await async_client.delete("/api/v1/match/requests/missing", headers=auth_headers)

        assert resp.status_code == 404
