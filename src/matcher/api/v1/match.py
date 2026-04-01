from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_arq_pool, get_db
from matcher.auth.deps import get_current_user, require_role
from matcher.db.models import User
from matcher.db.repos.match import MatchRepo
from matcher.pipeline.orchestrator import match_single
from matcher.schemas.match import (
    BatchRequestAccepted,
    Candidate,
    MatchItemsPage,
    MatchRequestDetails,
    MatchRequestInput,
    MatchResponse,
    MatchResult,
    ProductRef,
)

router = APIRouter(tags=["Matching"])


def _to_match_result(item_result) -> MatchResult:
    """Convert orchestrator MatchItemResult to API MatchResult schema."""
    best = None
    if item_result.best_candidate:
        best = ProductRef(
            product_id=item_result.best_candidate["product_id"],
            name=item_result.best_candidate.get("name", ""),
            article=item_result.best_candidate.get("article"),
            brand=item_result.best_candidate.get("brand"),
            category_path=item_result.best_candidate.get("category_path"),
        )

    alternatives = []
    for alt in item_result.alternatives:
        alternatives.append(Candidate(
            product_id=alt["product_id"],
            name=alt.get("name", ""),
            article=alt.get("article"),
            brand=alt.get("brand"),
            retrieval_rank=alt.get("retrieval_rank", 0),
            lexical_score=alt.get("lexical_score"),
            semantic_score=alt.get("semantic_score"),
            rerank_score=alt.get("rerank_score"),
            rules_score=alt.get("rules_score"),
            final_score=alt.get("final_score"),
            reasons=alt.get("reasons", []),
        ))

    return MatchResult(
        request_item_id=item_result.request_item_id,
        line_id=item_result.line_id,
        raw_text=item_result.raw_text,
        normalized_text=item_result.normalized_text,
        extracted_attributes=item_result.extracted_attributes,
        status=item_result.status,
        confidence=item_result.confidence,
        best_candidate=best,
        alternatives=alternatives,
        reasons=item_result.reasons,
    )


@router.post("/match", response_model=MatchResponse)
async def match_sync(
    body: MatchRequestInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Synchronous matching for small inputs."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    repo = MatchRepo(db)

    # Persist request for history
    await repo.create_request(
        request_id=request_id,
        supplier_id=body.supplier_id,
        source_type=body.source_type or "api",
        submitted_by=current_user.username,
        total_items=len(body.items),
    )

    results = []
    auto_count = review_count = no_match_count = 0

    for item in body.items:
        item_result = await match_single(
            raw_text=item.raw_text,
            session=db,
            line_id=item.line_id,
            supplier_id=body.supplier_id,
        )
        result = _to_match_result(item_result)
        results.append(result)

        # Count
        if result.status == "auto_match":
            auto_count += 1
        elif result.status == "review_needed":
            review_count += 1
        else:
            no_match_count += 1

    # Update request as done
    await repo.update_request_status(
        request_id, "done",
        processed_items=len(results),
        auto_matched_items=auto_count,
        review_needed_items=review_count,
        no_match_items=no_match_count,
    )
    await db.commit()

    return MatchResponse(
        request_id=request_id,
        status="done",
        results=results,
    )


@router.post("/match/batch", response_model=BatchRequestAccepted, status_code=202)
async def match_batch(
    body: MatchRequestInput,
    db: AsyncSession = Depends(get_db),
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(get_current_user),
):
    """Async batch matching -- enqueue for background processing."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    repo = MatchRepo(db)

    # Store request
    await repo.create_request(
        request_id=request_id,
        supplier_id=body.supplier_id,
        source_type=body.source_type or "api",
        submitted_by=current_user.username,
        total_items=len(body.items),
    )

    # Store items
    items_data = [{"line_id": item.line_id, "raw_text": item.raw_text} for item in body.items]
    await repo.create_items(request_id, items_data)
    await db.commit()

    # Enqueue ARQ job
    await arq_pool.enqueue_job("batch_match", request_id)

    return BatchRequestAccepted(request_id=request_id, status="queued")


@router.get("/match/requests")
async def list_match_requests(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent match requests."""
    repo = MatchRepo(db)
    requests = await repo.list_requests(limit=limit)
    items = [
        MatchRequestDetails(
            request_id=r.request_id,
            supplier_id=r.supplier_id,
            status=r.status,
            total_items=r.total_items,
            processed_items=r.processed_items,
            auto_matched_items=r.auto_matched_items,
            review_needed_items=r.review_needed_items,
            no_match_items=r.no_match_items,
            created_at=r.created_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
        )
        for r in requests
    ]
    return {"items": items}


@router.get("/match/requests/{request_id}", response_model=MatchRequestDetails)
async def get_match_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = MatchRepo(db)
    request = await repo.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    return MatchRequestDetails(
        request_id=request.request_id,
        supplier_id=request.supplier_id,
        status=request.status,
        total_items=request.total_items,
        processed_items=request.processed_items,
        auto_matched_items=request.auto_matched_items,
        review_needed_items=request.review_needed_items,
        no_match_items=request.no_match_items,
        created_at=request.created_at,
        started_at=request.started_at,
        finished_at=request.finished_at,
    )


@router.get("/match/requests/{request_id}/items", response_model=MatchItemsPage)
async def get_match_request_items(
    request_id: str,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = MatchRepo(db)
    items, total = await repo.get_request_items(request_id, status_filter=status, page=page, page_size=page_size)

    results = []
    for item in items:
        results.append(MatchResult(
            request_item_id=item.request_item_id,
            line_id=item.line_id,
            raw_text=item.raw_text,
            normalized_text=item.normalized_text,
            extracted_attributes=item.extracted_attributes or {},
            status=item.status,
            confidence=float(item.confidence) if item.confidence else None,
            reasons=item.reasons_json if isinstance(item.reasons_json, list) else [],
        ))

    return MatchItemsPage(page=page, page_size=page_size, total=total, items=results)


@router.get("/match/items/{request_item_id}/candidates")
async def get_item_candidates(
    request_item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = MatchRepo(db)
    candidates = await repo.get_item_candidates(request_item_id)
    return {"request_item_id": request_item_id, "candidates": candidates}


@router.delete("/match/requests/{request_id}", status_code=200)
async def delete_match_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """Delete a match request and all its items/candidates."""
    repo = MatchRepo(db)
    deleted = await repo.delete_request(request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Request not found")
    await db.commit()
    return {"ok": True, "request_id": request_id}
