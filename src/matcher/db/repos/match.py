from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import (
    CatalogProduct,
    GoldenLabel,
    MatchCandidate,
    MatchRequest,
    MatchRequestItem,
)


class MatchRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Match requests
    # ------------------------------------------------------------------

    async def create_request(
        self,
        request_id: str,
        supplier_id: str | None,
        source_type: str,
        submitted_by: str | None,
        total_items: int,
        file_name: str | None = None,
    ) -> MatchRequest:
        req = MatchRequest(
            request_id=request_id,
            supplier_id=supplier_id,
            source_type=source_type,
            submitted_by=submitted_by,
            status="queued",
            total_items=total_items,
            file_name=file_name,
        )
        self.session.add(req)
        await self.session.flush()
        return req

    async def list_requests(
        self,
        limit: int = 50,
        page: int = 1,
        status_filter: str | None = None,
        supplier_id: str | None = None,
        created_after: datetime | None = None,
    ) -> tuple[list[MatchRequest], int]:
        conditions = []
        if status_filter and status_filter != "all":
            conditions.append(MatchRequest.status == status_filter)
        if supplier_id and supplier_id != "all":
            conditions.append(MatchRequest.supplier_id == supplier_id)
        if created_after is not None:
            conditions.append(MatchRequest.created_at >= created_after)

        count_stmt = select(func.count()).select_from(MatchRequest)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))

        total = (await self.session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * limit
        stmt = select(MatchRequest).order_by(MatchRequest.created_at.desc())
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_request(self, request_id: str) -> MatchRequest | None:
        result = await self.session.execute(
            select(MatchRequest).where(MatchRequest.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def update_request_status(self, request_id: str, status: str, **counters: object) -> None:
        values: dict = {"status": status}
        if status == "running":
            values["started_at"] = datetime.now(UTC)
        elif status in ("done", "failed"):
            values["finished_at"] = datetime.now(UTC)
        values.update(counters)
        await self.session.execute(
            update(MatchRequest).where(MatchRequest.request_id == request_id).values(**values)
        )

    async def delete_request(self, request_id: str) -> bool:
        """Delete a match request and all its items/candidates (cascade)."""
        # Delete candidates first (items → candidates cascade may not be reliable)
        item_ids_stmt = select(MatchRequestItem.request_item_id).where(
            MatchRequestItem.request_id == request_id
        )
        await self.session.execute(
            delete(MatchCandidate).where(MatchCandidate.request_item_id.in_(item_ids_stmt))
        )
        # Delete items
        await self.session.execute(
            delete(MatchRequestItem).where(MatchRequestItem.request_id == request_id)
        )
        # Delete request
        result = await self.session.execute(
            delete(MatchRequest).where(MatchRequest.request_id == request_id)
        )
        return result.rowcount > 0

    async def clear_item_results(self, request_id: str) -> None:
        """Reset all items in a request to pending state for reprocessing."""
        # Delete candidates
        item_ids_stmt = select(MatchRequestItem.request_item_id).where(
            MatchRequestItem.request_id == request_id
        )
        await self.session.execute(
            delete(MatchCandidate).where(MatchCandidate.request_item_id.in_(item_ids_stmt))
        )
        # Reset item statuses
        await self.session.execute(
            update(MatchRequestItem)
            .where(MatchRequestItem.request_id == request_id)
            .values(
                status="no_match",
                best_product_id=None,
                confidence=None,
                normalized_text=None,
            )
        )

    # ------------------------------------------------------------------
    # Match request items
    # ------------------------------------------------------------------

    async def create_items(self, request_id: str, items: list[dict]) -> list[MatchRequestItem]:
        result: list[MatchRequestItem] = []
        for item in items:
            obj = MatchRequestItem(
                request_item_id=f"item_{uuid.uuid4().hex[:12]}",
                request_id=request_id,
                line_id=item.get("line_id"),
                raw_text=item["raw_text"],
                original_row_json=item.get("original_row"),
                status="no_match",
            )
            self.session.add(obj)
            result.append(obj)
        await self.session.flush()
        return result

    async def get_request_items(
        self,
        request_id: str,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[MatchRequestItem], int]:
        conditions = [MatchRequestItem.request_id == request_id]
        if status_filter:
            conditions.append(MatchRequestItem.status == status_filter)

        count_stmt = select(func.count()).select_from(MatchRequestItem).where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(MatchRequestItem)
            .where(and_(*conditions))
            .order_by(MatchRequestItem.created_at)
            .limit(page_size)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_item(self, request_item_id: str) -> MatchRequestItem | None:
        result = await self.session.execute(
            select(MatchRequestItem).where(MatchRequestItem.request_item_id == request_item_id)
        )
        return result.scalar_one_or_none()

    async def get_item_with_request(
        self, request_item_id: str
    ) -> tuple[MatchRequestItem | None, MatchRequest | None]:
        stmt = (
            select(MatchRequestItem, MatchRequest)
            .join(MatchRequest, MatchRequestItem.request_id == MatchRequest.request_id)
            .where(MatchRequestItem.request_item_id == request_item_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row:
            return row[0], row[1]
        return None, None

    async def update_item_result(
        self,
        request_item_id: str,
        *,
        status: str,
        best_product_id: str | None = None,
        confidence: float | None = None,
        normalized_text: str | None = None,
        extracted_attributes: dict | None = None,
        reasons_json: list | None = None,
        decision_trace_json: dict | None = None,
    ) -> None:
        values: dict = {"status": status}
        if best_product_id is not None:
            values["best_product_id"] = best_product_id
        if confidence is not None:
            values["confidence"] = confidence
        if normalized_text is not None:
            values["normalized_text"] = normalized_text
        if extracted_attributes is not None:
            values["extracted_attributes"] = extracted_attributes
        if reasons_json is not None:
            values["reasons_json"] = reasons_json
        if decision_trace_json is not None:
            values["decision_trace_json"] = decision_trace_json
        await self.session.execute(
            update(MatchRequestItem)
            .where(MatchRequestItem.request_item_id == request_item_id)
            .values(**values)
        )

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    async def save_candidates(self, request_item_id: str, candidates: list[dict]) -> None:
        for i, c in enumerate(candidates):
            obj = MatchCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:12]}",
                request_item_id=request_item_id,
                product_id=c["product_id"],
                retrieval_rank=i + 1,
                lexical_score=c.get("lexical_score"),
                semantic_score=c.get("semantic_score"),
                rerank_score=c.get("rerank_score"),
                rules_score=c.get("rules_score"),
                final_score=c.get("final_score"),
                reasons_json=c.get("reasons", []),
            )
            self.session.add(obj)
        await self.session.flush()

    async def get_item_candidates(self, request_item_id: str) -> list[dict]:
        stmt = (
            select(
                MatchCandidate.product_id,
                CatalogProduct.name,
                CatalogProduct.article,
                CatalogProduct.brand,
                MatchCandidate.retrieval_rank,
                MatchCandidate.lexical_score,
                MatchCandidate.semantic_score,
                MatchCandidate.rerank_score,
                MatchCandidate.rules_score,
                MatchCandidate.final_score,
                MatchCandidate.reasons_json,
            )
            .join(
                CatalogProduct,
                MatchCandidate.product_id == CatalogProduct.product_id,
            )
            .where(MatchCandidate.request_item_id == request_item_id)
            .order_by(MatchCandidate.final_score.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {
                "product_id": r.product_id,
                "name": r.name,
                "article": r.article,
                "brand": r.brand,
                "retrieval_rank": r.retrieval_rank,
                "lexical_score": float(r.lexical_score) if r.lexical_score else None,
                "semantic_score": float(r.semantic_score) if r.semantic_score else None,
                "rerank_score": float(r.rerank_score) if r.rerank_score else None,
                "rules_score": float(r.rules_score) if r.rules_score else None,
                "final_score": float(r.final_score) if r.final_score else None,
                "reasons": r.reasons_json if isinstance(r.reasons_json, list) else [],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    async def update_item_review(
        self,
        request_item_id: str,
        decision: str,
        final_product_id: str | None,
        reviewed_by: str,
        review_notes: str | None = None,
    ) -> None:
        values: dict = {
            "final_decision": decision,
            "final_product_id": final_product_id,
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(UTC),
        }
        if review_notes is not None:
            values["review_notes"] = review_notes
        await self.session.execute(
            update(MatchRequestItem)
            .where(MatchRequestItem.request_item_id == request_item_id)
            .values(**values)
        )

    # ------------------------------------------------------------------
    # Golden labels
    # ------------------------------------------------------------------

    async def create_golden_label(
        self,
        raw_query: str,
        normalized_query: str | None,
        supplier_id: str | None,
        product_id: str | None,
        label_type: str,
        source: str = "review",
    ) -> None:
        label = GoldenLabel(
            label_id=f"label_{uuid.uuid4().hex[:12]}",
            raw_query=raw_query,
            normalized_query=normalized_query,
            supplier_id=supplier_id,
            product_id=product_id,
            label_type=label_type,
            source=source,
        )
        self.session.add(label)
        await self.session.flush()

    # ------------------------------------------------------------------
    # Review queue
    # ------------------------------------------------------------------

    async def get_review_queue(
        self,
        *,
        supplier_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        """Get items needing review across all requests."""
        conditions = [
            MatchRequestItem.status == "review_needed",
            MatchRequestItem.final_decision.is_(None),
        ]
        if supplier_id:
            conditions.append(MatchRequest.supplier_id == supplier_id)

        where = and_(*conditions)
        base = (
            select(MatchRequestItem, MatchRequest.supplier_id, MatchRequest.file_name)
            .join(MatchRequest, MatchRequestItem.request_id == MatchRequest.request_id)
            .where(where)
        )

        count_result = await self.session.execute(
            select(func.count(MatchRequestItem.request_item_id))
            .select_from(MatchRequestItem)
            .join(MatchRequest, MatchRequestItem.request_id == MatchRequest.request_id)
            .where(where)
        )
        total = count_result.scalar() or 0

        stmt = (
            base.order_by(MatchRequestItem.confidence.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.all()), total
