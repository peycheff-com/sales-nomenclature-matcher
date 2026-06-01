from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matcher.worker import tasks


class _Session:
    def __init__(self) -> None:
        self.commit = AsyncMock()

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None


def _db_factory(session: _Session | None = None):
    session = session or _Session()

    def factory() -> _Session:
        return session

    return factory


def _sequence_db_factory(*sessions: _Session):
    remaining = list(sessions)

    def factory() -> _Session:
        return remaining.pop(0) if remaining else _Session()

    return factory


@pytest.mark.asyncio
async def test_process_batch_persists_success_error_progress_and_flushes():
    repo = MagicMock()
    repo.update_item_result = AsyncMock()
    repo.save_candidates = AsyncMock()
    repo.update_request_status = AsyncMock()
    synonym_repo = MagicMock()
    synonym_repo.build_synonym_map = AsyncMock(return_value={"насос": "pump"})
    tracker = MagicMock()
    tracker.flush = AsyncMock()
    ctx = SimpleNamespace(text="normalized pump")
    result = SimpleNamespace(
        status="auto_match",
        best_candidate={"product_id": "p1"},
        confidence=0.98,
        normalized_text="normalized pump",
        extracted_attributes={"brand": "Brand"},
        reasons=["reason"],
        decision_trace={"stage": "test"},
        alternatives=[
            {
                "product_id": "p1",
                "lexical_score": 0.7,
                "semantic_score": 0.8,
                "rerank_score": 0.9,
                "rules_score": 0.1,
                "final_score": 0.98,
                "reasons": ["good"],
            }
        ],
    )

    with (
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
        patch("matcher.db.repos.synonym.SynonymRepo", return_value=synonym_repo),
        patch("matcher.normalization.pipeline.run_pipeline", return_value=ctx),
        patch(
            "matcher.normalization.db_synonyms.apply_db_synonyms",
            new=AsyncMock(return_value=ctx),
        ),
        patch("matcher.indexing.embedder.embed_texts", new=AsyncMock(return_value=[[0.1], [0.2]])),
        patch(
            "matcher.pipeline.orchestrator.match_single",
            new=AsyncMock(side_effect=[result, RuntimeError("pipeline failed")]),
        ) as match_single,
    ):
        counters = await tasks._process_batch(
            db_factory=_db_factory(),
            request_id="req1",
            item_rows=[
                {"request_item_id": "i1", "raw_text": "Pump", "line_id": "1"},
                {"request_item_id": "i2", "raw_text": "Bad", "line_id": "2"},
            ],
            supplier_id="s1",
            tracker=tracker,
            commit_every=1,
            max_concurrency=1,
        )

    assert counters == {"auto": 1, "review": 0, "no_match": 1, "processed": 2}
    synonym_repo.build_synonym_map.assert_awaited_once_with(supplier_id="s1")
    assert match_single.await_count == 2
    first_call = match_single.await_args_list[0].kwargs
    assert first_call["pre_normalized_ctx"] is ctx
    assert first_call["query_embedding"] == [0.1]
    assert first_call["synonym_map"] == {"насос": "pump"}
    repo.save_candidates.assert_awaited_once_with(
        "i1",
        [
            {
                "product_id": "p1",
                "lexical_score": 0.7,
                "semantic_score": 0.8,
                "rerank_score": 0.9,
                "rules_score": 0.1,
                "final_score": 0.98,
                "reasons": ["good"],
            }
        ],
    )
    assert repo.update_item_result.await_args_list[-1].kwargs == {
        "status": "no_match",
        "confidence": 0.0,
        "decision_trace_json": {"error": "pipeline failed", "stage": "pipeline"},
    }
    assert repo.update_item_result.await_args_list[-1].args == ("i2",)
    final_status = repo.update_request_status.await_args_list[-1]
    assert final_status.args[:2] == ("req1", "done")
    assert final_status.kwargs["processed_items"] == 2
    tracker.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_batch_continues_when_progress_or_error_recording_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tasks.settings, "llm_matcher_enabled", False)
    repo = MagicMock()
    repo.update_item_result = AsyncMock(side_effect=[None, RuntimeError("write failed")])
    repo.save_candidates = AsyncMock()
    repo.update_request_status = AsyncMock(side_effect=[RuntimeError("progress down"), None])
    tracker = MagicMock()
    tracker.flush = AsyncMock()
    ctx = SimpleNamespace(text="normalized pump")
    result = SimpleNamespace(
        status="no_match",
        best_candidate=None,
        confidence=0.0,
        normalized_text="normalized pump",
        extracted_attributes={},
        reasons=[],
        decision_trace={},
        alternatives=[],
    )

    with (
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
        patch("matcher.db.repos.synonym.SynonymRepo") as SynonymRepo,
        patch("matcher.normalization.pipeline.run_pipeline", return_value=ctx),
        patch("matcher.indexing.embedder.embed_texts", new=AsyncMock(return_value=[[0.1], [0.2]])),
        patch(
            "matcher.pipeline.orchestrator.match_single",
            new=AsyncMock(side_effect=[result, RuntimeError("pipeline failed")]),
        ),
    ):
        SynonymRepo.return_value.build_synonym_map = AsyncMock(return_value={})
        counters = await tasks._process_batch(
            db_factory=_db_factory(),
            request_id="req_defensive",
            item_rows=[
                {"request_item_id": "i1", "raw_text": "Pump", "line_id": "1"},
                {"request_item_id": "i2", "raw_text": "Bad", "line_id": "2"},
            ],
            supplier_id=None,
            tracker=tracker,
            commit_every=1,
            max_concurrency=1,
        )

    assert counters == {"auto": 0, "review": 0, "no_match": 2, "processed": 2}
    assert repo.update_item_result.await_count == 2
    assert repo.update_request_status.await_args_list[-1].args[:2] == ("req_defensive", "done")


@pytest.mark.asyncio
async def test_process_batch_marks_request_failed_when_outer_batch_fails():
    repo = MagicMock()
    repo.update_request_status = AsyncMock()
    tracker = MagicMock()
    tracker.flush = AsyncMock()

    async def failing_gather(*aws):
        for awaitable in aws:
            awaitable.close()
        raise RuntimeError("batch exploded")

    with (
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
        patch("matcher.db.repos.synonym.SynonymRepo") as SynonymRepo,
        patch("matcher.worker.tasks.asyncio.gather", new=failing_gather),
    ):
        SynonymRepo.return_value.build_synonym_map = AsyncMock(return_value={})
        counters = await tasks._process_batch(
            db_factory=_db_factory(),
            request_id="req_failed",
            item_rows=[],
            supplier_id=None,
            tracker=tracker,
        )

    assert counters == {"auto": 0, "review": 0, "no_match": 0, "processed": 0}
    repo.update_request_status.assert_awaited_once()
    assert repo.update_request_status.await_args.kwargs["error_message"] == "batch exploded"

    failing_session = _Session()
    failing_session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    with (
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
        patch("matcher.db.repos.synonym.SynonymRepo") as SynonymRepo,
        patch.object(tasks.settings, "llm_matcher_enabled", False),
        patch("matcher.worker.tasks.asyncio.gather", new=failing_gather),
    ):
        SynonymRepo.return_value.build_synonym_map = AsyncMock(return_value={})
        counters = await tasks._process_batch(
            db_factory=_sequence_db_factory(_Session(), failing_session),
            request_id="req_failed_commit",
            item_rows=[],
            supplier_id=None,
            tracker=tracker,
        )

    assert counters["processed"] == 0


@pytest.mark.asyncio
async def test_process_batch_uses_bulk_llm_results_and_handles_prep_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    repo = MagicMock()
    repo.update_item_result = AsyncMock()
    repo.save_candidates = AsyncMock()
    repo.update_request_status = AsyncMock()
    synonym_repo = MagicMock()
    synonym_repo.build_synonym_map = AsyncMock(side_effect=RuntimeError("synonyms down"))
    tracker = MagicMock()
    tracker.flush = AsyncMock()
    good_ctx = SimpleNamespace(text="normalized good")
    llm_result = SimpleNamespace(product_id="p1")
    match_result = SimpleNamespace(
        status="review_needed",
        best_candidate=None,
        confidence=0.8,
        normalized_text="normalized good",
        extracted_attributes={},
        reasons=[],
        decision_trace={},
        alternatives=[],
    )

    def run_pipeline(raw_text: str):
        if raw_text == "Bad normalize":
            raise ValueError("normalize failed")
        return good_ctx

    class Features:
        def to_dict(self) -> dict:
            return {"brand": "Brand"}

    monkeypatch.setattr(tasks.settings, "llm_matcher_enabled", True)
    with (
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
        patch("matcher.db.repos.synonym.SynonymRepo", return_value=synonym_repo),
        patch("matcher.normalization.pipeline.run_pipeline", side_effect=run_pipeline),
        patch(
            "matcher.indexing.embedder.embed_texts",
            new=AsyncMock(side_effect=RuntimeError("embed down")),
        ),
        patch("matcher.pipeline.features.extract_features", return_value=Features()),
        patch(
            "matcher.pipeline.llm_matcher.get_cached_catalog",
            new=AsyncMock(return_value=["catalog"]),
        ),
        patch(
            "matcher.pipeline.llm_matcher.llm_match_batch",
            new=AsyncMock(return_value=[llm_result, None]),
        ),
        patch(
            "matcher.pipeline.orchestrator.match_single",
            new=AsyncMock(return_value=match_result),
        ) as match_single,
    ):
        counters = await tasks._process_batch(
            db_factory=_db_factory(),
            request_id="req_llm",
            item_rows=[
                {"request_item_id": "i1", "raw_text": "Good", "line_id": "1"},
                {"request_item_id": "i2", "raw_text": "Bad normalize", "line_id": "2"},
            ],
            supplier_id=None,
            tracker=tracker,
            commit_every=50,
            max_concurrency=1,
        )

    assert counters == {"auto": 0, "review": 2, "no_match": 0, "processed": 2}
    assert match_single.await_args_list[0].kwargs["pre_llm_result"] is llm_result
    assert match_single.await_args_list[1].kwargs["pre_normalized_ctx"] is None
    assert match_single.await_args_list[1].kwargs["query_embedding"] is ...


@pytest.mark.asyncio
async def test_do_catalog_import_dry_run_returns_parsed_count(tmp_path):
    upload_path = tmp_path / "catalog.csv"
    upload_path.write_text("name\nPump\n", encoding="utf-8")

    with patch("matcher.ingestion.file_adapter.parse_file", return_value=[{"name": "Pump"}]):
        result = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_dry",
            "csv",
            file_path=str(upload_path),
            dry_run=True,
        )

    assert result == {
        "job_id": "job_dry",
        "status": "done",
        "parsed_count": 1,
        "dry_run": True,
    }
    assert upload_path.exists() is False


@pytest.mark.asyncio
async def test_do_catalog_import_deletes_uploaded_file_when_parse_fails(tmp_path):
    upload_path = tmp_path / "catalog.csv"
    upload_path.write_text("bad", encoding="utf-8")

    with patch("matcher.ingestion.file_adapter.parse_file", side_effect=ValueError("bad parse")):
        result = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_parse_bad",
            "csv",
            file_path=str(upload_path),
        )

    assert result == {"job_id": "job_parse_bad", "status": "failed", "error": "bad parse"}
    assert upload_path.exists() is False


@pytest.mark.asyncio
async def test_do_catalog_import_upserts_valid_products_and_reports_transform_errors(
    tmp_path,
):
    upload_path = tmp_path / "catalog.csv"
    upload_path.write_text("name\nPump\nBad\n", encoding="utf-8")
    product = {"product_id": "p1", "name": "Pump"}
    repo = MagicMock()
    repo.upsert_products = AsyncMock(return_value=1)

    def transform(raw):
        if raw["name"] == "Bad":
            raise ValueError("bad row")
        return product

    with (
        patch(
            "matcher.ingestion.file_adapter.parse_file",
            return_value=[{"name": "Pump"}, {"name": "Bad"}],
        ),
        patch("matcher.ingestion.transformer.transform_item", side_effect=transform),
        patch("matcher.db.repos.catalog.CatalogRepo", return_value=repo),
        patch("matcher.indexing.search.invalidate_catalog_count") as invalidate_count,
        patch("matcher.pipeline.llm_matcher.invalidate_catalog_cache") as invalidate_cache,
    ):
        result = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_ok",
            "csv",
            file_path=str(upload_path),
        )

    assert result["status"] == "done"
    assert result["upserted"] == 1
    assert result["errors"] == 1
    assert result["error_details"][0]["row"] == 1
    repo.upsert_products.assert_awaited_once_with([product])
    invalidate_count.assert_called_once()
    invalidate_cache.assert_called_once()


@pytest.mark.asyncio
async def test_do_catalog_import_fails_when_all_rows_are_invalid(tmp_path):
    upload_path = tmp_path / "catalog.csv"
    upload_path.write_text("name\nBad\n", encoding="utf-8")

    with (
        patch("matcher.ingestion.file_adapter.parse_file", return_value=[{"name": "Bad"}]),
        patch("matcher.ingestion.transformer.transform_item", side_effect=ValueError("bad row")),
    ):
        result = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_bad",
            "csv",
            file_path=str(upload_path),
        )

    assert result["status"] == "failed"
    assert "0 valid products" in result["error"]
    assert result["error_details"][0]["error"] == "bad row"


@pytest.mark.asyncio
async def test_do_catalog_import_handles_onec_fetch_failures_and_dry_run():
    with patch(
        "matcher.ingestion.onec_adapter.fetch_onec_catalog",
        side_effect=RuntimeError("1c down"),
    ):
        failed = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_1c_fail",
            "onec_api",
        )
    assert failed == {"job_id": "job_1c_fail", "status": "failed", "error": "1c down"}

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.ingestion.onec_adapter.fetch_onec_catalog", return_value=[{"name": "Pump"}]),
    ):
        done = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_1c_dry",
            "onec_api",
            dry_run=True,
        )

    assert done["status"] == "done"
    assert done["parsed_count"] == 1


@pytest.mark.asyncio
async def test_do_catalog_import_blocks_invalid_file_url():
    with patch("matcher.worker.tasks.validate_url_safe", side_effect=tasks.SSRFError("blocked")):
        result = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_ssrf",
            "csv",
            file_url="https://example.com/catalog.csv",
        )

    assert result["status"] == "failed"
    assert "Invalid file URL" in result["error"]


@pytest.mark.asyncio
async def test_catalog_import_reports_existing_lock_and_download_failure():
    redis = MagicMock()
    redis.set = AsyncMock(return_value=False)

    locked = await tasks.catalog_import(
        {"db_factory": _db_factory(), "redis": redis},
        "job_locked",
        "csv",
        file_url="https://example.com/catalog.csv",
    )

    assert locked == {
        "job_id": "job_locked",
        "status": "failed",
        "error": "Another import is already running",
    }

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def get(self, _url: str):
            raise RuntimeError("download down")

    with (
        patch("matcher.worker.tasks.validate_url_safe"),
        patch("matcher.worker.tasks.httpx.AsyncClient", lambda timeout: Client()),
    ):
        failed = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_download_bad",
            "csv",
            file_url="https://example.com/catalog.csv",
        )

    assert failed == {
        "job_id": "job_download_bad",
        "status": "failed",
        "error": "download down",
    }


@pytest.mark.asyncio
async def test_do_catalog_import_downloads_remote_file_and_handles_parse_errors():
    class Response:
        content = b"name\nPump\n"

        def raise_for_status(self) -> None:
            return None

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def get(self, url: str) -> Response:
            assert url == "https://example.com/catalog.xlsx"
            return Response()

    with (
        patch("matcher.worker.tasks.validate_url_safe"),
        patch("matcher.worker.tasks.httpx.AsyncClient", lambda timeout: Client()),
        patch("matcher.ingestion.file_adapter.parse_file", side_effect=ValueError("bad file")),
    ):
        failed = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_remote_bad",
            "xlsx",
            file_url="https://example.com/catalog.xlsx",
        )

    assert failed == {"job_id": "job_remote_bad", "status": "failed", "error": "bad file"}

    with (
        patch("matcher.worker.tasks.validate_url_safe"),
        patch("matcher.worker.tasks.httpx.AsyncClient", lambda timeout: Client()),
        patch("matcher.ingestion.file_adapter.parse_file", return_value=[{"name": "Pump"}]),
    ):
        dry = await tasks._do_catalog_import(
            {"db_factory": _db_factory()},
            "job_remote_ok",
            "xlsx",
            file_url="https://example.com/catalog.xlsx",
            dry_run=True,
        )

    assert dry["status"] == "done"
    assert dry["parsed_count"] == 1


@pytest.mark.asyncio
async def test_catalog_import_continues_when_redis_locking_or_delete_fails():
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    redis.delete = AsyncMock(side_effect=RuntimeError("delete down"))

    with patch(
        "matcher.worker.tasks._do_catalog_import",
        new=AsyncMock(return_value={"status": "done"}),
    ):
        result = await tasks.catalog_import(
            {"db_factory": _db_factory(), "redis": redis}, "job", "csv"
        )

    assert result == {"status": "done"}

    redis.set = AsyncMock(return_value=True)
    with patch(
        "matcher.worker.tasks._do_catalog_import",
        new=AsyncMock(return_value={"status": "done"}),
    ):
        result = await tasks.catalog_import(
            {"db_factory": _db_factory(), "redis": redis}, "job", "csv"
        )

    assert result == {"status": "done"}
    redis.delete.assert_awaited_once_with("lock:catalog_import")


@pytest.mark.asyncio
async def test_catalog_reindex_loads_settings_reindexes_and_invalidates():
    reindex_result = {
        "index_version_id": "idx1",
        "total_products": 3,
        "embedded_count": 3,
        "embedding_model": "model",
        "embedding_version": "v2",
    }

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()) as load_settings,
        patch(
            "matcher.indexing.indexer.reindex_catalog",
            new=AsyncMock(return_value=reindex_result),
        ) as reindex,
        patch("matcher.indexing.search.invalidate_catalog_count") as invalidate_count,
        patch("matcher.pipeline.llm_matcher.invalidate_catalog_cache") as invalidate_cache,
    ):
        result = await tasks.catalog_reindex(
            {"db_factory": _db_factory()},
            "job_reindex",
            embedding_model="model",
            embedding_version="v2",
        )

    assert result == {"job_id": "job_reindex", "status": "done", **reindex_result}
    load_settings.assert_awaited_once()
    reindex.assert_awaited_once()
    assert reindex.await_args.kwargs["embedding_model"] == "model"
    assert reindex.await_args.kwargs["session_factory"] is not None
    invalidate_count.assert_called_once()
    invalidate_cache.assert_called_once()


@pytest.mark.asyncio
async def test_smart_upload_returns_failed_when_request_missing():
    repo = MagicMock()
    repo.get_request = AsyncMock(return_value=None)

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.db.repos.match.MatchRepo", return_value=repo),
    ):
        result = await tasks.smart_upload({"db_factory": _db_factory()}, "missing")

    assert result == {"request_id": "missing", "status": "failed", "error": "not found"}


@pytest.mark.asyncio
async def test_smart_upload_ingests_catalog_reindexes_and_processes_batch():
    catalog_repo = MagicMock()
    catalog_repo.upsert_products = AsyncMock(return_value=1)
    match_repo = MagicMock()
    match_repo.get_request = AsyncMock(return_value=SimpleNamespace(supplier_id="s1"))
    match_repo.update_request_status = AsyncMock()
    match_repo.get_request_items = AsyncMock(
        return_value=([SimpleNamespace(request_item_id="i1", raw_text="Pump", line_id="1")], 1)
    )

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.ingestion.transformer.transform_item", return_value={"product_id": "p1"}),
        patch("matcher.db.repos.catalog.CatalogRepo", return_value=catalog_repo),
        patch("matcher.db.repos.match.MatchRepo", return_value=match_repo),
        patch("matcher.indexing.indexer.reindex_catalog", new=AsyncMock()) as reindex,
        patch(
            "matcher.worker.tasks._process_batch",
            new=AsyncMock(return_value={"processed": 1, "auto": 1, "review": 0, "no_match": 0}),
        ) as process_batch,
    ):
        result = await tasks.smart_upload(
            {"db_factory": _db_factory()},
            "req1",
            catalog_items=[{"raw_text": "Catalog pump", "unit": "pcs"}],
            catalog_count=1,
        )

    assert result == {
        "request_id": "req1",
        "status": "done",
        "catalog_upserted": 1,
        "catalog_errors": 0,
        "matched": 1,
    }
    catalog_repo.upsert_products.assert_awaited_once()
    reindex.assert_awaited_once()
    process_batch.assert_awaited_once()
    assert process_batch.await_args.kwargs["item_rows"] == [
        {"request_item_id": "i1", "raw_text": "Pump", "line_id": "1"}
    ]


@pytest.mark.asyncio
async def test_batch_match_and_smart_upload_load_request_items_across_pages():
    first = SimpleNamespace(request_item_id="i1", raw_text="Pump", line_id="1")
    second = SimpleNamespace(request_item_id="i2", raw_text="Cable", line_id="2")

    batch_repo = MagicMock()
    batch_repo.get_request = AsyncMock(return_value=SimpleNamespace(supplier_id="s1"))
    batch_repo.update_request_status = AsyncMock()
    batch_repo.get_request_items = AsyncMock(side_effect=[([first], 2), ([second], 2)])

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.db.repos.match.MatchRepo", return_value=batch_repo),
        patch(
            "matcher.worker.tasks._process_batch",
            new=AsyncMock(return_value={"processed": 2, "auto": 0, "review": 2, "no_match": 0}),
        ) as process_batch,
    ):
        result = await tasks.batch_match({"db_factory": _db_factory()}, "req_pages")

    assert result == {"request_id": "req_pages", "status": "done", "processed": 2}
    assert [call.kwargs["page"] for call in batch_repo.get_request_items.await_args_list] == [1, 2]
    assert process_batch.await_args.kwargs["item_rows"] == [
        {"request_item_id": "i1", "raw_text": "Pump", "line_id": "1"},
        {"request_item_id": "i2", "raw_text": "Cable", "line_id": "2"},
    ]

    smart_repo = MagicMock()
    smart_repo.get_request = AsyncMock(return_value=SimpleNamespace(supplier_id=None))
    smart_repo.update_request_status = AsyncMock()
    smart_repo.get_request_items = AsyncMock(side_effect=[([first], 2), ([second], 2)])

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.db.repos.match.MatchRepo", return_value=smart_repo),
        patch(
            "matcher.worker.tasks._process_batch",
            new=AsyncMock(return_value={"processed": 2, "auto": 1, "review": 1, "no_match": 0}),
        ) as process_batch,
    ):
        result = await tasks.smart_upload(
            {"db_factory": _db_factory()},
            "req_smart_pages",
            catalog_items=[],
            catalog_count=0,
        )

    assert result["matched"] == 2
    assert [call.kwargs["page"] for call in smart_repo.get_request_items.await_args_list] == [1, 2]
    assert process_batch.await_args.kwargs["item_rows"][-1]["request_item_id"] == "i2"


@pytest.mark.asyncio
async def test_smart_upload_counts_catalog_transform_errors_and_skips_reindex():
    match_repo = MagicMock()
    match_repo.get_request = AsyncMock(return_value=SimpleNamespace(supplier_id=None))
    match_repo.update_request_status = AsyncMock()
    match_repo.get_request_items = AsyncMock(return_value=([], 0))

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch(
            "matcher.ingestion.transformer.transform_item",
            side_effect=ValueError("bad catalog"),
        ),
        patch("matcher.db.repos.match.MatchRepo", return_value=match_repo),
        patch("matcher.indexing.indexer.reindex_catalog", new=AsyncMock()) as reindex,
        patch(
            "matcher.worker.tasks._process_batch",
            new=AsyncMock(return_value={"processed": 0, "auto": 0, "review": 0, "no_match": 0}),
        ),
    ):
        result = await tasks.smart_upload(
            {"db_factory": _db_factory()},
            "req1",
            catalog_items=[{"raw_text": "Bad"}],
            catalog_count=1,
        )

    assert result["catalog_upserted"] == 0
    assert result["catalog_errors"] == 1
    assert result["matched"] == 0
    reindex.assert_not_awaited()


@pytest.mark.asyncio
async def test_smart_upload_continues_when_reindex_fails():
    catalog_repo = MagicMock()
    catalog_repo.upsert_products = AsyncMock(return_value=1)
    match_repo = MagicMock()
    match_repo.get_request = AsyncMock(return_value=SimpleNamespace(supplier_id=None))
    match_repo.update_request_status = AsyncMock()
    match_repo.get_request_items = AsyncMock(return_value=([], 0))

    with (
        patch("matcher.api.v1.settings.load_persisted_settings", new=AsyncMock()),
        patch("matcher.ingestion.transformer.transform_item", return_value={"product_id": "p1"}),
        patch("matcher.db.repos.catalog.CatalogRepo", return_value=catalog_repo),
        patch("matcher.db.repos.match.MatchRepo", return_value=match_repo),
        patch(
            "matcher.indexing.indexer.reindex_catalog",
            new=AsyncMock(side_effect=RuntimeError("reindex failed")),
        ),
        patch(
            "matcher.worker.tasks._process_batch",
            new=AsyncMock(return_value={"processed": 0, "auto": 0, "review": 0, "no_match": 0}),
        ),
    ):
        result = await tasks.smart_upload(
            {"db_factory": _db_factory()},
            "req1",
            catalog_items=[{"raw_text": "Catalog"}],
            catalog_count=1,
        )

    assert result["status"] == "done"
    assert result["catalog_upserted"] == 1
    assert result["matched"] == 0
