from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import httpx

from matcher.config import settings
from matcher.security.url_validator import SSRFError, validate_url_safe

logger = logging.getLogger(__name__)


async def batch_match(ctx: dict, request_id: str) -> dict:
    """Process a batch match request.

    Uses a fresh DB session per commit window (every 50 items) to avoid stale
    connections on long-running batches.
    """
    from matcher.db.repos.match import MatchRepo
    from matcher.pipeline.orchestrator import match_single
    from matcher.api.v1.settings import load_persisted_settings

    db_factory = ctx["db_factory"]
    logger.info("Starting batch_match for request %s", request_id)

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

        items, _total = await repo.get_request_items(request_id, page=1, page_size=10000)
        item_rows = [
            {"request_item_id": it.request_item_id, "raw_text": it.raw_text, "line_id": it.line_id}
            for it in items
        ]

    auto_count = 0
    review_count = 0
    no_match_count = 0
    processed = 0
    COMMIT_EVERY = 50

    try:
        for item in item_rows:
            try:
                async with db_factory() as session:
                    repo = MatchRepo(session)
                    result = await match_single(
                        raw_text=item["raw_text"],
                        session=session,
                        line_id=item["line_id"],
                        supplier_id=supplier_id,
                        auto_threshold=settings.auto_match_threshold,
                        review_threshold=settings.review_threshold,
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
                        decision_trace_json=result.decision_trace if hasattr(result, "decision_trace") else None,
                    )

                    candidates_data = []
                    for alt in result.alternatives:
                        candidates_data.append({
                            "product_id": alt["product_id"],
                            "lexical_score": alt.get("lexical_score"),
                            "semantic_score": alt.get("semantic_score"),
                            "rerank_score": alt.get("rerank_score"),
                            "rules_score": alt.get("rules_score"),
                            "final_score": alt.get("final_score"),
                            "reasons": alt.get("reasons", []),
                        })
                    if candidates_data:
                        await repo.save_candidates(item["request_item_id"], candidates_data)

                    if result.status == "auto_match":
                        auto_count += 1
                    elif result.status == "review_needed":
                        review_count += 1
                    else:
                        no_match_count += 1

                    processed += 1

                    # Progress update every COMMIT_EVERY items
                    if processed % COMMIT_EVERY == 0:
                        await repo.update_request_status(
                            request_id, "running",
                            processed_items=processed,
                            auto_matched_items=auto_count,
                            review_needed_items=review_count,
                            no_match_items=no_match_count,
                        )

                    await session.commit()

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
                no_match_count += 1
                processed += 1

        # Final status update
        async with db_factory() as session:
            repo = MatchRepo(session)
            await repo.update_request_status(
                request_id, "done",
                processed_items=processed,
                auto_matched_items=auto_count,
                review_needed_items=review_count,
                no_match_items=no_match_count,
            )
            await session.commit()
        logger.info("Batch match %s done: %d processed", request_id, processed)

    except Exception as e:
        logger.exception("Batch match %s failed", request_id)
        try:
            async with db_factory() as session:
                repo = MatchRepo(session)
                await repo.update_request_status(
                    request_id, "failed",
                    processed_items=processed,
                    auto_matched_items=auto_count,
                    review_needed_items=review_count,
                    no_match_items=no_match_count,
                    error_message=str(e),
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to mark request %s as failed", request_id)

    return {"request_id": request_id, "status": "done", "processed": processed}


async def catalog_import(ctx: dict, job_id: str, source_type: str, **kwargs) -> dict:
    """Import catalog from CSV/XLSX file."""
    redis = ctx.get("redis")
    lock_key = "lock:catalog_import"
    if redis:
        acquired = await redis.set(lock_key, job_id, ex=3600, nx=True)
        if not acquired:
            return {"job_id": job_id, "status": "failed", "error": "Another import is already running"}
    try:
        return await _do_catalog_import(ctx, job_id, source_type, **kwargs)
    finally:
        if redis:
            await redis.delete(lock_key)


async def _do_catalog_import(ctx: dict, job_id: str, source_type: str, **kwargs) -> dict:
    """Inner implementation of catalog import (called under Redis lock)."""
    from matcher.db.repos.catalog import CatalogRepo
    from matcher.ingestion.file_adapter import parse_file
    from matcher.ingestion.transformer import transform_item
    from matcher.api.v1.settings import load_persisted_settings

    db_factory = ctx["db_factory"]
    file_url = kwargs.get("file_url")
    file_path = kwargs.get("file_path")  # Direct file upload path
    dry_run = kwargs.get("dry_run", False)

    if source_type not in ("csv", "xlsx", "onec_api"):
        logger.warning("Unsupported source_type: %s", source_type)
        return {"job_id": job_id, "status": "failed", "error": f"Unsupported source_type: {source_type}"}

    if source_type in ("csv", "xlsx") and not file_url and not file_path:
        return {"job_id": job_id, "status": "failed", "error": "file_url or file_path is required for file imports"}

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
            if tmp_path: tmp_path.unlink(missing_ok=True)
            return {"job_id": job_id, "status": "failed", "error": str(e)}

    try:
        if dry_run:
            return {"job_id": job_id, "status": "done", "parsed_count": len(raw_items), "dry_run": True}

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
    from matcher.indexing.indexer import reindex_catalog
    from matcher.api.v1.settings import load_persisted_settings

    logger.info("Starting reindex job %s", job_id)
    db_factory = ctx.get("db_factory")
    
    async with db_factory() as session:
        await load_persisted_settings(session, force=True)
    result = await reindex_catalog(
        embedding_model=kwargs.get("embedding_model"),
        embedding_version=kwargs.get("embedding_version"),
        session_factory=db_factory,
    )
    logger.info("Reindex job %s complete: %s", job_id, result)
    return {"job_id": job_id, "status": "done", **result}


async def smart_upload(ctx: dict, request_id: str, **kwargs) -> dict:
    """Smart upload pipeline: catalog ingest → reindex → batch match.

    Receives pre-extracted catalog items and the request_id for supplier items
    that are already stored in the database.

    Steps:
        1. Ingest catalog items into catalog_products (normalize + upsert)
        2. Reindex embeddings for new catalog entries
        3. Run batch matching on the supplier items
    """
    import uuid
    from matcher.db.repos.catalog import CatalogRepo
    from matcher.db.repos.match import MatchRepo
    from matcher.ingestion.base import RawCatalogItem
    from matcher.ingestion.transformer import transform_item
    from matcher.indexing.indexer import reindex_catalog
    from matcher.pipeline.orchestrator import match_single
    from matcher.api.v1.settings import load_persisted_settings

    db_factory = ctx["db_factory"]
    catalog_items = kwargs.get("catalog_items", [])
    catalog_count = kwargs.get("catalog_count", 0)

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

        items, _total = await repo.get_request_items(request_id, page=1, page_size=10000)
        item_rows = [
            {"request_item_id": it.request_item_id, "raw_text": it.raw_text, "line_id": it.line_id}
            for it in items
        ]

    auto_count = 0
    review_count = 0
    no_match_count = 0
    processed = 0
    COMMIT_EVERY = 50

    try:
        for item in item_rows:
            try:
                async with db_factory() as session:
                    repo = MatchRepo(session)
                    result = await match_single(
                        raw_text=item["raw_text"],
                        session=session,
                        line_id=item["line_id"],
                        supplier_id=supplier_id,
                        auto_threshold=settings.auto_match_threshold,
                        review_threshold=settings.review_threshold,
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
                        decision_trace_json=result.decision_trace if hasattr(result, "decision_trace") else None,
                    )

                    candidates_data = []
                    for alt in result.alternatives:
                        candidates_data.append({
                            "product_id": alt["product_id"],
                            "lexical_score": alt.get("lexical_score"),
                            "semantic_score": alt.get("semantic_score"),
                            "rerank_score": alt.get("rerank_score"),
                            "rules_score": alt.get("rules_score"),
                            "final_score": alt.get("final_score"),
                            "reasons": alt.get("reasons", []),
                        })
                    if candidates_data:
                        await repo.save_candidates(item["request_item_id"], candidates_data)

                    if result.status == "auto_match":
                        auto_count += 1
                    elif result.status == "review_needed":
                        review_count += 1
                    else:
                        no_match_count += 1

                    processed += 1

                    if processed % COMMIT_EVERY == 0:
                        await repo.update_request_status(
                            request_id, "running",
                            processed_items=processed,
                            auto_matched_items=auto_count,
                            review_needed_items=review_count,
                            no_match_items=no_match_count,
                        )

                    await session.commit()

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
                no_match_count += 1
                processed += 1

        # Final status
        async with db_factory() as session:
            repo = MatchRepo(session)
            await repo.update_request_status(
                request_id, "done",
                processed_items=processed,
                auto_matched_items=auto_count,
                review_needed_items=review_count,
                no_match_items=no_match_count,
            )
            await session.commit()

        logger.info(
            "Smart upload %s done: catalog=%d, matched=%d",
            request_id, upserted, processed,
        )

    except Exception as e:
        logger.exception("Smart upload %s failed at match phase", request_id)
        try:
            async with db_factory() as session:
                repo = MatchRepo(session)
                await repo.update_request_status(
                    request_id, "failed",
                    processed_items=processed,
                    auto_matched_items=auto_count,
                    review_needed_items=review_count,
                    no_match_items=no_match_count,
                    error_message=str(e),
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to mark request %s as failed", request_id)

    return {
        "request_id": request_id,
        "status": "done",
        "catalog_upserted": upserted,
        "catalog_errors": len(catalog_errors),
        "matched": processed,
    }

