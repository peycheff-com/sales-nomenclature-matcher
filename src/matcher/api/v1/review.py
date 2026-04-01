from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user
from matcher.db.models import CatalogProduct, User
from matcher.db.repos.audit import AuditRepo
from matcher.db.repos.catalog import CatalogRepo
from matcher.db.repos.match import MatchRepo
from matcher.db.repos.supplier import SupplierRepo
from matcher.normalization.pipeline import run_pipeline
from matcher.schemas.review import (
    BatchReviewInput,
    BatchReviewResult,
    ReviewInput,
    ReviewResult,
)

router = APIRouter(tags=["Review"])


@router.post("/review/items/{request_item_id}", response_model=ReviewResult)
async def review_item(
    request_item_id: str,
    body: ReviewInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept, correct, or reject a match result."""
    match_repo = MatchRepo(db)

    # Verify item exists and get associated request (lock row to prevent concurrent reviews)
    item, request = await match_repo.get_item_with_request(request_item_id, for_update=True)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.final_decision and item.reviewed_by != current_user.username:
        raise HTTPException(
            status_code=409,
            detail="Item already reviewed by another user. Refresh to see latest state.",
        )

    # Determine final product ID
    final_product_id = body.final_product_id
    if body.final_decision == "accepted" and not final_product_id:
        # Accept the best candidate
        final_product_id = item.best_product_id

    if body.final_decision == "corrected" and final_product_id:
        product = await db.get(CatalogProduct, final_product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found in catalog")

    # Update the review
    await match_repo.update_item_review(
        request_item_id=request_item_id,
        decision=body.final_decision,
        final_product_id=final_product_id,
        reviewed_by=current_user.username,
        review_notes=body.comment,
    )

    # Create golden label for training data
    label_type = "positive" if body.final_decision in ("accepted", "corrected") else "negative"
    await match_repo.create_golden_label(
        raw_query=item.raw_text,
        normalized_query=item.normalized_text or item.raw_text,
        supplier_id=request.supplier_id if request else None,
        product_id=final_product_id,
        label_type=label_type,
        source="review",
    )

    # Audit log
    audit = AuditRepo(db)
    await audit.log(
        action="review",
        entity_type="match_request_item",
        entity_id=request_item_id,
        user_id=current_user.user_id,
        username=current_user.username,
        details={
            "decision": body.final_decision,
            "final_product_id": final_product_id,
            "create_alias": body.create_alias,
            "create_supplier_mapping": body.create_supplier_mapping,
        },
    )

    # Optionally create alias
    if body.create_alias and final_product_id:
        ctx = run_pipeline(item.raw_text)
        catalog_repo = CatalogRepo(db)
        await catalog_repo.create_alias(
            product_id=final_product_id,
            alias_text=item.raw_text,
            normalized_text=ctx.text or item.raw_text,
            alias_type="user_added",
            created_by=current_user.username,
        )
        await audit.log(
            action="alias_create",
            entity_type="catalog_alias",
            entity_id=final_product_id,
            user_id=current_user.user_id,
            username=current_user.username,
            details={"alias_text": item.raw_text, "source": "review"},
        )

    # Optionally create supplier mapping
    if body.create_supplier_mapping and final_product_id and request and request.supplier_id:
        ctx = run_pipeline(item.raw_text)
        supplier_repo = SupplierRepo(db)
        await supplier_repo.create_mapping(
            supplier_id=request.supplier_id,
            data={
                "supplier_raw_text": item.raw_text,
                "normalized_supplier_text": ctx.text or item.raw_text,
                "product_id": final_product_id,
                "mapping_type": "approved",
                "confidence": float(item.confidence) if item.confidence else None,
                "approved_by": current_user.username,
            },
        )
        await audit.log(
            action="mapping_create",
            entity_type="supplier_mapping",
            entity_id=request.supplier_id,
            user_id=current_user.user_id,
            username=current_user.username,
            details={
                "supplier_raw_text": item.raw_text,
                "product_id": final_product_id,
            },
        )

    await db.commit()

    return ReviewResult(ok=True, request_item_id=request_item_id)


@router.post("/review/batch", response_model=BatchReviewResult)
async def batch_review_items(
    body: BatchReviewInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process multiple review acceptances in a single bulk transaction."""
    match_repo = MatchRepo(db)
    catalog_repo = CatalogRepo(db)
    supplier_repo = SupplierRepo(db)
    audit = AuditRepo(db)

    processed_count = 0
    for req_item in body.items:
        item, request = await match_repo.get_item_with_request(req_item.request_item_id)
        if not item:
            continue

        final_product_id = req_item.final_product_id
        if req_item.final_decision == "accepted" and not final_product_id:
            final_product_id = item.best_product_id

        if req_item.final_decision == "corrected" and final_product_id:
            product = await db.get(CatalogProduct, final_product_id)
            if not product:
                continue

        await match_repo.update_item_review(
            request_item_id=req_item.request_item_id,
            decision=req_item.final_decision,
            final_product_id=final_product_id,
            reviewed_by=current_user.username,
            review_notes=req_item.comment,
        )

        label_type = (
            "positive" if req_item.final_decision in ("accepted", "corrected") else "negative"
        )
        await match_repo.create_golden_label(
            raw_query=item.raw_text,
            normalized_query=item.normalized_text or item.raw_text,
            supplier_id=request.supplier_id if request else None,
            product_id=final_product_id,
            label_type=label_type,
            source="review_batch",
        )

        await audit.log(
            action="review",
            entity_type="match_request_item",
            entity_id=req_item.request_item_id,
            user_id=current_user.user_id,
            username=current_user.username,
            details={
                "decision": req_item.final_decision,
                "final_product_id": final_product_id,
                "batch": True,
            },
        )

        if req_item.create_alias and final_product_id:
            ctx = run_pipeline(item.raw_text)
            await catalog_repo.create_alias(
                product_id=final_product_id,
                alias_text=item.raw_text,
                normalized_text=ctx.text or item.raw_text,
                alias_type="user_added",
                created_by=current_user.username,
            )

        if (
            req_item.create_supplier_mapping
            and final_product_id
            and request
            and request.supplier_id
        ):
            ctx = run_pipeline(item.raw_text)
            await supplier_repo.create_mapping(
                supplier_id=request.supplier_id,
                data={
                    "supplier_raw_text": item.raw_text,
                    "normalized_supplier_text": ctx.text or item.raw_text,
                    "product_id": final_product_id,
                    "mapping_type": "approved",
                    "confidence": float(item.confidence) if item.confidence else None,
                    "approved_by": current_user.username,
                },
            )

        processed_count += 1

    await db.commit()
    return BatchReviewResult(ok=True, processed_count=processed_count)
