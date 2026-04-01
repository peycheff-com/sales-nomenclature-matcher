from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx

from matcher.config import settings
from matcher.security.url_validator import SSRFError, validate_url_safe

logger = logging.getLogger(__name__)


async def _process_batch(
    *,
    db_factory,
    request_id: str,
    item_rows: list[dict],
    supplier_id: str | None,
    tracker,
    auto_threshold: float | None = None,
    review_threshold: float | None = None,
    commit_every: int = 50,
    max_concurrency: int | None = None,
) -> dict:
    """Process a list of match items concurrently, persisting results per item.

    Uses a semaphore to limit concurrent processing. Each item gets its own
    DB session for isolation.

    Returns {"auto": int, "review": int, "no_match": int, "processed": int}.
    """
    from matcher.db.repos.match import MatchRepo
    from matcher.db.repos.synonym import SynonymRepo
    from matcher.indexing.embedder import embed_texts
    from matcher.normalization.db_synonyms import apply_db_synonyms
    from matcher.normalization.pipeline import NormalizationContext, run_pipeline
    from matcher.pipeline.orchestrator import match_single

    if max_concurrency is None:
        max_concurrency = settings.batch_concurrency

    sem = asyncio.Semaphore(max_concurrency)
    lock = asyncio.Lock()
    counters = {"auto": 0, "review": 0, "no_match": 0, "processed": 0}

    effective_auto = auto_threshold if auto_threshold is not None else settings.auto_match_threshold
    effective_review = (
        review_threshold if review_threshold is not None else settings.review_threshold
    )

    # Pre-load synonym map once for the entire batch
    cached_synonym_map: dict[str, str] | None = None
    try:
        async with db_factory() as session:
            synonym_repo = SynonymRepo(session)
            cached_synonym_map = await synonym_repo.build_synonym_map(supplier_id=supplier_id)
    except Exception:
        logger.warning("Failed to pre-load synonym map, will load per item")

    # ── Phase 1: Pre-normalize all items ────────────────────────────────────
    pre_normalized: dict[str, NormalizationContext] = {}
    for item in item_rows:
        try:
            ctx = run_pipeline(item["raw_text"])
            if cached_synonym_map:
                ctx = await apply_db_synonyms(
                    ctx, None, supplier_id, synonym_map=cached_synonym_map
                )
            pre_normalized[item["request_item_id"]] = ctx
        except Exception as e:
            logger.warning("Pre-normalization failed for %s: %s", item["request_item_id"], e)

    # ── Phase 2: Batch-embed all normalized texts ───────────────────────────
    pre_embeddings: dict[str, list[float]] = {}
    items_with_ctx = [it for it in item_rows if it["request_item_id"] in pre_normalized]
    if items_with_ctx:
        try:
            all_texts = [pre_normalized[it["request_item_id"]].text for it in items_with_ctx]
            all_embs = await embed_texts(all_texts, batch_size=100, token_tracker=tracker)
            for i, it in enumerate(items_with_ctx):
                if all_embs[i]:
                    pre_embeddings[it["request_item_id"]] = all_embs[i]
        except Exception as e:
            logger.warning("Batch embedding failed, items will embed individually: %s", e)

    async def _process_one(item: dict) -> None:
        async with sem:
            try:
                async with db_factory() as session:
                    repo = MatchRepo(session)
                    rid = item["request_item_id"]
                    result = await match_single(
                        raw_text=item["raw_text"],
                        session=session,
                        line_id=item["line_id"],
                        supplier_id=supplier_id,
                        auto_threshold=effective_auto,
                        review_threshold=effective_review,
                        token_tracker=tracker,
                        synonym_map=cached_synonym_map,
                        pre_normalized_ctx=pre_normalized.get(rid),
                        query_embedding=pre_embeddings.get(rid, ...),
                    )

                    best_product_id = None
                    if result.best_candidate:
                        best_product_id = result.best_candidate["product_id"]

                    await repo.update_item_result(
                        item["request_item_id"],
                        status=result.status,
                        best_product_id=best_product_id,
                        confidence=result.confidence,
                        normalized_text=result.normalized_text,
                        extracted_attributes=result.extracted_attributes,
                        reasons_json=result.reasons,
                        decision_trace_json=result.decision_trace or None,
                    )

                    candidates_data = []
                    for alt in result.alternatives:
                        candidates_data.append(
                            {
                                "product_id": alt["product_id"],
                                "lexical_score": alt.get("lexical_score"),
                                "semantic_score": alt.get("semantic_score"),
                                "rerank_score": alt.get("rerank_score"),
                                "rules_score": alt.get("rules_score"),
                                "final_score": alt.get("final_score"),
                                "reasons": alt.get("reasons", []),
                            }
                        )
                    if candidates_data:
                        await repo.save_candidates(item["request_item_id"], candidates_data)

                    await session.commit()

                # Update counters outside the DB session
                should_report = False
                async with lock:
                    if result.status == "auto_match":
                        counters["auto"] += 1
                    elif result.status == "review_needed":
                        counters["review"] += 1
                    else:
                        counters["no_match"] += 1
                    counters["processed"] += 1
                    should_report = counters["processed"] % commit_every == 0
                    snapshot = dict(counters) if should_report else None

                # Progress update outside the lock to avoid blocking other items
                if should_report:
                    try:
                        async with db_factory() as progress_session:
                            progress_repo = MatchRepo(progress_session)
                            await progress_repo.update_request_status(
                                request_id,
                                "running",
                                processed_items=snapshot["processed"],
                                auto_matched_items=snapshot["auto"],
                                review_needed_items=snapshot["review"],
                                no_match_items=snapshot["no_match"],
                            )
                            await progress_session.commit()
                    except Exception:
                        logger.warning("Failed to report progress for %s", request_id)

            except Exception as exc:
                logger.exception("Error processing item %s", item["request_item_id"])
                try:
                    async with db_factory() as err_session:
                        err_repo = MatchRepo(err_session)
                        await err_repo.update_item_result(
                            item["request_item_id"],
                            status="no_match",
                            confidence=0.0,
                            decision_trace_json={"error": str(exc), "stage": "pipeline"},
                        )
                        await err_session.commit()
                except Exception:
                    logger.exception("Failed to record error for item %s", item["request_item_id"])
                async with lock:
                    counters["no_match"] += 1
                    counters["processed"] += 1

    try:
        await asyncio.gather(*[_process_one(item) for item in item_rows])

        # Final status update + flush token tracking
        async with db_factory() as session:
            repo = MatchRepo(session)
            await repo.update_request_status(
                request_id,
                "done",
                processed_items=counters["processed"],
                auto_matched_items=counters["auto"],
                review_needed_items=counters["review"],
                no_match_items=counters["no_match"],
            )
            await tracker.flush(session)
            await session.commit()

    except Exception as e:
        logger.exception("Batch processing for %s failed", request_id)
        try:
            async with db_factory() as session:
                repo = MatchRepo(session)
                await repo.update_request_status(
                    request_id,
                    "failed",
                    processed_items=counters["processed"],
                    auto_matched_items=counters["auto"],
                    review_needed_items=counters["review"],
                    no_match_items=counters["no_match"],
                    error_message=str(e),
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to mark request %s as failed", request_id)

    return counters


async def batch_match(ctx: dict, request_id: str) -> dict:
    """Process a batch match request."""
    from matcher.api.v1.settings import load_persisted_settings
    from matcher.db.repos.match import MatchRepo
    from matcher.pipeline.token_tracker import TokenTracker

    db_factory = ctx["db_factory"]
    logger.info("Starting batch_match for request %s", request_id)

    tracker = TokenTracker(request_id=request_id)

    # Load request metadata and item IDs into memory with a short-lived session
    async with db_factory() as session:
        await load_persisted_settings(session, force=True)
        repo = MatchRepo(session)
        request = await repo.get_request(request_id)
        if not request:
            logger.error("Request %s not found", request_id)
            return {"request_id": request_id, "status": "failed", "error": "not found"}

        supplier_id = request.supplier_id
        await repo.update_request_status(request_id, "running")
        await session.commit()

        # Load all item rows in pages to avoid massive single query
        item_rows = []
        page = 1
        while True:
            items, total = await repo.get_request_items(request_id, page=page, page_size=500)
            for it in items:
                item_rows.append(
                    {
                        "request_item_id": it.request_item_id,
                        "raw_text": it.raw_text,
                        "line_id": it.line_id,
                    }
                )
            if len(item_rows) >= total or not items:
                break
            page += 1

    counters = await _process_batch(
        db_factory=db_factory,
        request_id=request_id,
        item_rows=item_rows,
        supplier_id=supplier_id,
        tracker=tracker,
    )

    logger.info(
        "Batch match %s done: %d processed, %d tokens used (~$%.4f)",
        request_id,
        counters["processed"],
        tracker.total_tokens,
        tracker.total_cost,
    )

    return {"request_id": request_id, "status": "done", "processed": counters["processed"]}


async def catalog_import(ctx: dict, job_id: str, source_type: str, **kwargs) -> dict:
    """Import catalog from CSV/XLSX file."""
    redis = ctx.get("redis")
    lock_key = "lock:catalog_import"
    lock_acquired = False
    if redis:
        try:
            acquired = await redis.set(lock_key, job_id, ex=600, nx=True)
            if not acquired:
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "error": "Another import is already running",
                }
            lock_acquired = True
        except Exception:
            logger.warning("Redis unavailable for import lock, proceeding without lock")
    try:
        return await _do_catalog_import(ctx, job_id, source_type, **kwargs)
    finally:
        if redis and lock_acquired:
            try:
                await redis.delete(lock_key)
            except Exception:
                logger.warning("Failed to release import lock")


async def _do_catalog_import(ctx: dict, job_id: str, source_type: str, **kwargs) -> dict:
    """Inner implementation of catalog import (called under Redis lock)."""
    from matcher.api.v1.settings import load_persisted_settings
    from matcher.db.repos.catalog import CatalogRepo
    from matcher.ingestion.file_adapter import parse_file
    from matcher.ingestion.transformer import transform_item

    db_factory = ctx["db_factory"]
    file_url = kwargs.get("file_url")
    file_path = kwargs.get("file_path")  # Direct file upload path
    dry_run = kwargs.get("dry_run", False)

    if source_type not in ("csv", "xlsx", "onec_api"):
        logger.warning("Unsupported source_type: %s", source_type)
        return {
            "job_id": job_id,
            "status": "failed",
            "error": f"Unsupported source_type: {source_type}",
        }

    if source_type in ("csv", "xlsx") and not file_url and not file_path:
        return {
            "job_id": job_id,
            "status": "failed",
            "error": "file_url or file_path is required for file imports",
        }

    # Validate file_url to prevent SSRF
    if file_url:
        try:
            validate_url_safe(file_url, allow_http=False)
        except SSRFError as e:
            logger.warning("SSRF blocked for catalog import: %s -> %s", file_url, e)
            return {"job_id": job_id, "status": "failed", "error": f"Invalid file URL: {e}"}

    logger.info("Starting catalog import job %s from %s", job_id, source_type)

    raw_items = []
    tmp_path = None

    if source_type == "onec_api":
        from matcher.ingestion.onec_adapter import fetch_onec_catalog

        try:
            async with db_factory() as session:
                await load_persisted_settings(session, force=True)
            raw_items = await fetch_onec_catalog(dry_run=dry_run)
            logger.info("Fetched %d items from 1C API", len(raw_items))
        except Exception as e:
            return {"job_id": job_id, "status": "failed", "error": str(e)}
    elif file_path:
        # Direct file upload — file already on disk
        tmp_path = Path(file_path)
    else:
        # Download file from URL
        suffix = ".xlsx" if source_type == "xlsx" else ".csv"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
        except Exception as e:
            logger.exception("Failed to download file: %s", file_url)
            return {"job_id": job_id, "status": "failed", "error": str(e)}

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            # Parse file
            raw_items = parse_file(str(tmp_path))
            logger.info("Parsed %d items from %s", len(raw_items), file_url)
        except Exception as e:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)
            return {"job_id": job_id, "status": "failed", "error": str(e)}

    try:
        if dry_run:
            return {
                "job_id": job_id,
                "status": "done",
                "parsed_count": len(raw_items),
                "dry_run": True,
            }

        # Transform items
        products = []
        errors = []
        for i, raw in enumerate(raw_items):
            try:
                product = transform_item(raw)
                products.append(product)
            except Exception as e:
                errors.append({"row": i, "error": str(e)})

        # Upsert to database
        async with db_factory() as session:
            repo = CatalogRepo(session)
            count = await repo.upsert_products(products)
            await session.commit()

        from matcher.indexing.search import invalidate_catalog_count
        from matcher.pipeline.llm_matcher import invalidate_catalog_cache

        invalidate_catalog_count()
        invalidate_catalog_cache()

        logger.info("Catalog import %s: %d upserted, %d errors", job_id, count, len(errors))
        return {
            "job_id": job_id,
            "status": "done",
            "upserted": count,
            "errors": len(errors),
            "error_details": errors[:20],
        }

    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


async def catalog_reindex(ctx: dict, job_id: str, **kwargs) -> dict:
    """Rebuild embeddings and search indexes."""
    from matcher.api.v1.settings import load_persisted_settings
    from matcher.indexing.indexer import reindex_catalog

    logger.info("Starting reindex job %s", job_id)
    db_factory = ctx.get("db_factory")

    async with db_factory() as session:
        await load_persisted_settings(session, force=True)
    result = await reindex_catalog(
        embedding_model=kwargs.get("embedding_model"),
        embedding_version=kwargs.get("embedding_version"),
        session_factory=db_factory,
    )
    from matcher.indexing.search import invalidate_catalog_count
    from matcher.pipeline.llm_matcher import invalidate_catalog_cache

    invalidate_catalog_count()
    invalidate_catalog_cache()

    logger.info("Reindex job %s complete: %s", job_id, result)
    return {"job_id": job_id, "status": "done", **result}


async def smart_upload(ctx: dict, request_id: str, **kwargs) -> dict:
    """Smart upload pipeline: catalog ingest -> reindex -> batch match.

    Receives pre-extracted catalog items and the request_id for supplier items
    that are already stored in the database.

    Steps:
        1. Ingest catalog items into catalog_products (normalize + upsert)
        2. Reindex embeddings for new catalog entries
        3. Run batch matching on the supplier items
    """
    import uuid

    from matcher.api.v1.settings import load_persisted_settings
    from matcher.db.repos.catalog import CatalogRepo
    from matcher.db.repos.match import MatchRepo
    from matcher.indexing.indexer import reindex_catalog
    from matcher.ingestion.base import RawCatalogItem
    from matcher.ingestion.transformer import transform_item
    from matcher.pipeline.token_tracker import TokenTracker

    db_factory = ctx["db_factory"]
    catalog_items = kwargs.get("catalog_items", [])
    catalog_count = kwargs.get("catalog_count", 0)

    tracker = TokenTracker(request_id=request_id)

    logger.info(
        "Starting smart_upload for request %s (catalog=%d items)",
        request_id,
        catalog_count,
    )

    # Load persisted settings once
    async with db_factory() as session:
        await load_persisted_settings(session, force=True)

    # --- Step 1: Ingest catalog items ---
    upserted = 0
    catalog_errors: list[dict] = []
    if catalog_items:
        logger.info("Ingesting %d catalog items", len(catalog_items))
        products: list[dict] = []
        for i, ci in enumerate(catalog_items):
            try:
                raw = RawCatalogItem(
                    product_id=f"prd_{uuid.uuid4().hex[:12]}",
                    name=ci["raw_text"],
                    unit=ci.get("unit"),
                )
                product = transform_item(raw)
                products.append(product)
            except Exception as e:
                catalog_errors.append({"row": i, "error": str(e)})

        if products:
            async with db_factory() as session:
                repo = CatalogRepo(session)
                upserted = await repo.upsert_products(products)
                await session.commit()
            logger.info("Catalog upsert: %d products", upserted)

    # --- Step 2: Reindex if catalog was ingested ---
    if upserted > 0:
        logger.info("Reindexing after catalog ingestion (%d new products)", upserted)
        try:
            await reindex_catalog(session_factory=db_factory)
            logger.info("Reindex complete")
        except Exception as e:
            logger.warning("Reindex failed (matching will proceed with existing index): %s", e)

    # --- Step 3: Batch match supplier items ---
    logger.info("Starting batch match phase for request %s", request_id)

    async with db_factory() as session:
        repo = MatchRepo(session)
        request = await repo.get_request(request_id)
        if not request:
            logger.error("Request %s not found", request_id)
            return {"request_id": request_id, "status": "failed", "error": "not found"}

        supplier_id = request.supplier_id
        await repo.update_request_status(request_id, "running")
        await session.commit()

        # Load all item rows in pages to avoid massive single query
        item_rows = []
        page = 1
        while True:
            items, total = await repo.get_request_items(request_id, page=page, page_size=500)
            for it in items:
                item_rows.append(
                    {
                        "request_item_id": it.request_item_id,
                        "raw_text": it.raw_text,
                        "line_id": it.line_id,
                    }
                )
            if len(item_rows) >= total or not items:
                break
            page += 1

    counters = await _process_batch(
        db_factory=db_factory,
        request_id=request_id,
        item_rows=item_rows,
        supplier_id=supplier_id,
        tracker=tracker,
    )

    logger.info(
        "Smart upload %s done: catalog=%d, matched=%d, tokens=%d",
        request_id,
        upserted,
        counters["processed"],
        tracker.total_tokens,
    )

    return {
        "request_id": request_id,
        "status": "done",
        "catalog_upserted": upserted,
        "catalog_errors": len(catalog_errors),
        "matched": counters["processed"],
    }
