from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from matcher.db.repos.match import MatchRepo


class _Scalars:
    def __init__(self, values: list) -> None:
        self.values = values

    def all(self) -> list:
        return self.values


class _Result:
    def __init__(
        self,
        *,
        scalar_value=None,
        scalar_one_or_none_value=None,
        scalar_values: list | None = None,
        rows: list | None = None,
        rowcount: int = 0,
    ) -> None:
        self._scalar_value = scalar_value
        self._scalar_one_or_none_value = scalar_one_or_none_value
        self._scalar_values = scalar_values or []
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalar_one_or_none_value

    def scalars(self) -> _Scalars:
        return _Scalars(self._scalar_values)

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.execute = AsyncMock(side_effect=self._execute)
        self.flush = AsyncMock()
        self.add = MagicMock()

    async def _execute(self, _statement):
        if not self.results:
            raise AssertionError("No fake result queued")
        return self.results.pop(0)


def _last_params(session: _Session) -> dict:
    statement = session.execute.await_args.args[0]
    return statement.compile().params


@pytest.mark.asyncio
async def test_match_request_crud_listing_and_recovery_paths():
    request = SimpleNamespace(request_id="req_1")
    session = _Session(
        _Result(scalar_value=2),
        _Result(scalar_values=[request]),
        _Result(scalar_one_or_none_value=request),
        _Result(scalar_values=[request]),
    )
    repo = MatchRepo(session)

    created = await repo.create_request(
        "req_new",
        supplier_id="sup_1",
        source_type="upload",
        submitted_by="usr_1",
        total_items=3,
        file_name="items.xlsx",
        job_payload={"request_id": "req_new"},
    )
    assert created.request_id == "req_new"
    assert created.job_name == "batch_match"
    assert created.job_payload_json == {"request_id": "req_new"}
    session.add.assert_called_once_with(created)
    assert session.flush.await_count == 1

    rows, total = await repo.list_requests(
        status_filter="queued",
        supplier_id="sup_1",
        created_after=datetime.now(UTC),
    )
    assert rows == [request]
    assert total == 2
    assert await repo.get_request("req_1") is request
    assert await repo.list_recoverable_requests() == [request]


@pytest.mark.asyncio
async def test_update_request_status_sets_lifecycle_timestamps_and_counters():
    session = _Session(_Result(), _Result(), _Result())
    repo = MatchRepo(session)

    await repo.update_request_status("req_1", "running", processed_items=1)
    running_params = _last_params(session)
    assert running_params["status"] == "running"
    assert running_params["processed_items"] == 1
    assert running_params["started_at"].tzinfo is not None
    assert running_params["finished_at"] is None

    await repo.update_request_status("req_1", "queued")
    queued_params = _last_params(session)
    assert queued_params["status"] == "queued"
    assert queued_params["started_at"] is None
    assert queued_params["finished_at"] is None

    await repo.update_request_status("req_1", "failed", error_message="worker lost")
    failed_params = _last_params(session)
    assert failed_params["status"] == "failed"
    assert failed_params["error_message"] == "worker lost"
    assert failed_params["finished_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_delete_request_returns_rowcount_and_clear_item_results_executes_reset():
    session = _Session(_Result(), _Result(), _Result(rowcount=1), _Result(), _Result())
    repo = MatchRepo(session)

    assert await repo.delete_request("req_1") is True
    await repo.clear_item_results("req_1")
    assert session.execute.await_count == 5

    missing_session = _Session(_Result(), _Result(), _Result(rowcount=0))
    assert await MatchRepo(missing_session).delete_request("missing") is False


@pytest.mark.asyncio
async def test_match_item_create_read_and_join_paths():
    item = SimpleNamespace(request_item_id="item_1")
    request = SimpleNamespace(request_id="req_1")
    session = _Session(
        _Result(scalar_value=1),
        _Result(scalar_values=[item]),
        _Result(scalar_one_or_none_value=item),
        _Result(rows=[(item, request)]),
        _Result(rows=[]),
    )
    repo = MatchRepo(session)

    created = await repo.create_items(
        "req_1",
        [
            {"line_id": "1", "raw_text": "цемент 25 кг", "original_row": {"qty": 2}},
            {"raw_text": "paint"},
        ],
    )
    assert [obj.request_id for obj in created] == ["req_1", "req_1"]
    assert created[0].request_item_id.startswith("item_")
    assert created[0].line_id == "1"
    assert created[0].status == "no_match"
    assert session.add.call_count == 2
    assert session.flush.await_count == 1

    rows, total = await repo.get_request_items("req_1", status_filter="review_needed")
    assert rows == [item]
    assert total == 1
    assert await repo.get_item("item_1") is item
    assert await repo.get_item_with_request("item_1", for_update=True) == (item, request)
    assert await repo.get_item_with_request("missing") == (None, None)


@pytest.mark.asyncio
async def test_update_item_result_and_review_only_include_supplied_optional_fields():
    session = _Session(_Result(), _Result())
    repo = MatchRepo(session)

    await repo.update_item_result(
        "item_1",
        status="auto_match",
        best_product_id="prod_1",
        confidence=0.97,
        normalized_text="cement 25 kg",
        extracted_attributes={"unit": "kg"},
        reasons_json=["exact article"],
        decision_trace_json={"gate": "article"},
    )
    params = _last_params(session)
    assert params["status"] == "auto_match"
    assert params["best_product_id"] == "prod_1"
    assert params["confidence"] == 0.97
    assert params["normalized_text"] == "cement 25 kg"
    assert params["extracted_attributes"] == {"unit": "kg"}
    assert params["reasons_json"] == ["exact article"]
    assert params["decision_trace_json"] == {"gate": "article"}

    await repo.update_item_review(
        "item_1",
        decision="corrected",
        final_product_id="prod_2",
        reviewed_by="usr_1",
        review_notes="Picked corrected product",
    )
    review_params = _last_params(session)
    assert review_params["final_decision"] == "corrected"
    assert review_params["final_product_id"] == "prod_2"
    assert review_params["reviewed_by"] == "usr_1"
    assert review_params["review_notes"] == "Picked corrected product"
    assert review_params["reviewed_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_candidates_are_saved_and_formatted_for_item_view():
    rows = [
        SimpleNamespace(
            product_id="prod_1",
            name="Cement",
            article="A-1",
            brand="Brand",
            retrieval_rank=1,
            lexical_score=Decimal("0.80"),
            semantic_score=Decimal("0.70"),
            rerank_score=Decimal("0.60"),
            rules_score=Decimal("0.90"),
            final_score=Decimal("0.95"),
            reasons_json=["brand"],
        ),
        SimpleNamespace(
            product_id="prod_2",
            name="Paint",
            article=None,
            brand=None,
            retrieval_rank=2,
            lexical_score=Decimal("0"),
            semantic_score=None,
            rerank_score=None,
            rules_score=None,
            final_score=None,
            reasons_json={"not": "a list"},
        ),
    ]
    session = _Session(_Result(rows=rows))
    repo = MatchRepo(session)

    await repo.save_candidates(
        "item_1",
        [
            {"product_id": "prod_1", "final_score": 0.95, "reasons": ["brand"]},
            {"product_id": "prod_2", "semantic_score": 0.5},
        ],
    )
    assert session.add.call_count == 2
    saved = [call.args[0] for call in session.add.call_args_list]
    assert [candidate.retrieval_rank for candidate in saved] == [1, 2]
    assert saved[0].candidate_id.startswith("cand_")
    assert saved[0].reasons_json == ["brand"]
    assert saved[1].reasons_json == []
    assert session.flush.await_count == 1

    formatted = await repo.get_item_candidates("item_1")
    assert formatted == [
        {
            "product_id": "prod_1",
            "name": "Cement",
            "article": "A-1",
            "brand": "Brand",
            "retrieval_rank": 1,
            "lexical_score": 0.8,
            "semantic_score": 0.7,
            "rerank_score": 0.6,
            "rules_score": 0.9,
            "final_score": 0.95,
            "reasons": ["brand"],
        },
        {
            "product_id": "prod_2",
            "name": "Paint",
            "article": None,
            "brand": None,
            "retrieval_rank": 2,
            "lexical_score": None,
            "semantic_score": None,
            "rerank_score": None,
            "rules_score": None,
            "final_score": None,
            "reasons": [],
        },
    ]


@pytest.mark.asyncio
async def test_golden_labels_and_review_queue_paths():
    row = (SimpleNamespace(request_item_id="item_1"), "sup_1", "items.xlsx")
    session = _Session(_Result(scalar_value=1), _Result(rows=[row]))
    repo = MatchRepo(session)

    await repo.create_golden_label(
        raw_query="цемент",
        normalized_query="cement",
        supplier_id="sup_1",
        product_id="prod_1",
        label_type="positive",
    )
    label = session.add.call_args.args[0]
    assert label.label_id.startswith("label_")
    assert label.raw_query == "цемент"
    assert label.source == "review"
    assert session.flush.await_count == 1

    rows, total = await repo.get_review_queue(supplier_id="sup_1", page=2, page_size=10)
    assert rows == [row]
    assert total == 1
