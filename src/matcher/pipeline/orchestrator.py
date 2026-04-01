from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from matcher.config import settings
from matcher.db.repos.alias import AliasRepo
from matcher.db.repos.supplier import SupplierRepo
from matcher.db.repos.synonym import SynonymRepo
from matcher.indexing.embedder import embed_single
from matcher.indexing.search import hybrid_search
from matcher.normalization.db_synonyms import apply_db_synonyms
from matcher.normalization.pipeline import run_pipeline
from matcher.pipeline.agent import resolve_agentically
from matcher.pipeline.decision import decide
from matcher.pipeline.explanations import build_reasons
from matcher.pipeline.features import extract_features, extract_numbers_from_text
from matcher.pipeline.overrides import check_supplier_override
from matcher.pipeline.reranker import rerank_candidates
from matcher.pipeline.scoring import (
    compute_attribute_overlap,
    compute_pair_features,
    score_candidate,
)
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


@dataclass
class MatchItemResult:
    """Result for a single matched line."""

    request_item_id: str
    line_id: str | None
    raw_text: str
    normalized_text: str
    extracted_attributes: dict
    status: str
    confidence: float
    best_candidate: dict | None = None
    alternatives: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    decision_trace: dict = field(default_factory=dict)


async def match_single(
    raw_text: str,
    session: AsyncSession,
    line_id: str | None = None,
    supplier_id: str | None = None,
    strict_mode: bool = False,
    retrieval_top_n: int = 50,
    rerank_top_n: int = 10,
    auto_threshold: float | None = None,
    review_threshold: float | None = None,
    token_tracker: TokenTracker | None = None,
    synonym_map: dict[str, str] | None = None,
) -> MatchItemResult:
    """Run the full matching pipeline on a single input line."""
    request_item_id = f"item_{uuid.uuid4().hex[:12]}"

    # Stage 0.5: Fetch supplier profile for strict_mode and normalization rules
    supplier = None
    if supplier_id:
        supplier = await SupplierRepo(session).get_supplier(supplier_id)
        if supplier:
            strict_mode = supplier.strict_mode or strict_mode

    # Stage 1: Normalize (YAML-based pipeline)
    ctx = run_pipeline(raw_text)

    # Stage 1.5: Apply DB-driven synonyms (global + supplier-specific)
    synonym_repo = SynonymRepo(session)
    ctx = await apply_db_synonyms(ctx, synonym_repo, supplier_id, synonym_map=synonym_map)
    normalized_text = ctx.text

    # Stage 2: Extract features
    features = extract_features(ctx)
    extracted_attrs = features.to_dict()

    # Stage 0+3: Parallel override check and embedding (saves ~200ms/item)
    embed_task = asyncio.create_task(embed_single(normalized_text, token_tracker=token_tracker))

    override = await check_supplier_override(
        supplier_id=supplier_id,
        raw_text=raw_text,
        normalized_text=normalized_text,
        article_hint=features.article,
        session=session,
    )
    if override and override.mapping_type in ("exact", "approved"):
        embed_task.cancel()
        try:
            await embed_task
        except (asyncio.CancelledError, Exception):
            pass
        return MatchItemResult(
            request_item_id=request_item_id,
            line_id=line_id,
            raw_text=raw_text,
            normalized_text=normalized_text,
            extracted_attributes=extracted_attrs,
            status="auto_match",
            confidence=0.995,
            best_candidate={"product_id": override.product_id},
            reasons=["Найдено точное соответствие поставщика"],
            decision_trace={
                "short_circuit": "supplier_override",
                "mapping_type": override.mapping_type,
            },
        )

    # Await embedding result
    try:
        query_embedding = await embed_task
    except Exception as e:
        logger.warning("Pre-computed embedding failed: %s", e)
        query_embedding = None

    # Stage 3: Candidate retrieval (use pre-computed embedding)
    # Don't hard-filter by brand — scoring handles brand matching downstream
    candidates = await hybrid_search(
        query_text=raw_text,
        normalized_text=normalized_text,
        session=session,
        top_n=retrieval_top_n,
        token_tracker=token_tracker,
        query_embedding=query_embedding,
    )

    if not candidates:
        # Last resort: agent resolution when retrieval finds nothing
        if (
            settings.agentic_resolution_enabled
            and settings.active_llm_api_key
            and settings.active_llm_api_key not in ("", "none")
        ):
            agent_decision = await resolve_agentically(
                raw_text,
                [],
                session,
                extracted_attrs=extracted_attrs,
                token_tracker=token_tracker,
            )
            if agent_decision and agent_decision.get("product_id"):
                return MatchItemResult(
                    request_item_id=request_item_id,
                    line_id=line_id,
                    raw_text=raw_text,
                    normalized_text=normalized_text,
                    extracted_attributes=extracted_attrs,
                    status="review_needed",  # Never auto from 0-candidate agent
                    confidence=0.80,
                    best_candidate={"product_id": agent_decision["product_id"]},
                    alternatives=[],
                    reasons=[
                        f"Agent fallback: {agent_decision.get('reasoning', '')}",
                    ],
                    decision_trace={
                        "stage": "agent_fallback",
                        "candidates_found": 0,
                        "agent_decision": agent_decision,
                    },
                )

        return MatchItemResult(
            request_item_id=request_item_id,
            line_id=line_id,
            raw_text=raw_text,
            normalized_text=normalized_text,
            extracted_attributes=extracted_attrs,
            status="no_match",
            confidence=0.0,
            reasons=["Кандидаты не найдены"],
            decision_trace={"stage": "retrieval", "candidates_found": 0},
        )

    # Stage 3.5: Alias lookup
    alias_repo = AliasRepo(session)
    alias_product_ids = await alias_repo.find_product_ids_by_text(normalized_text)

    # Stage 4: Rerank
    reranked = await rerank_candidates(
        query=normalized_text,
        candidates=candidates,
        top_n=rerank_top_n,
        token_tracker=token_tracker,
    )

    # Stage 5+6: Score each reranked candidate
    scored_candidates = []
    for rr in reranked:
        c = rr.candidate
        candidate_numbers = extract_numbers_from_text(c.normalized_name or c.name)
        pair_features = compute_pair_features(
            query_brand=features.brand,
            query_numbers=features.numbers,
            query_unit=features.unit,
            query_packaging=features.packaging,
            query_category=None,
            candidate_brand=c.normalized_brand or c.brand,
            candidate_article=c.article,
            candidate_manufacturer_code=c.manufacturer_code,
            candidate_numbers=candidate_numbers,
            candidate_unit=c.unit,
            candidate_packaging=c.packaging,
            candidate_category=c.category_path,
            lexical_score=c.lexical_score,
            semantic_score=c.semantic_score,
            rerank_score=rr.rerank_score,
            alias_hit=c.product_id in alias_product_ids,
        )
        candidate_attrs = {
            "brand": c.normalized_brand or c.brand,
            "unit": c.unit,
            "numbers": candidate_numbers,
        }
        query_attrs = {
            "brand": features.brand,
            "unit": features.unit,
            "numbers": features.numbers,
        }
        pair_features.attribute_overlap_score = compute_attribute_overlap(
            query_attrs, candidate_attrs
        )
        scoring_result = score_candidate(pair_features)
        supplier_thresholds = supplier.normalization_rules.get("thresholds") if supplier else None
        decision = decide(
            scoring_result,
            strict_mode=strict_mode,
            auto_threshold=auto_threshold,
            review_threshold=review_threshold,
            supplier_thresholds=supplier_thresholds,
            category=c.category_path,
        )
        reasons = build_reasons(pair_features, scoring_result.short_circuit)

        scored_candidates.append(
            {
                "candidate": c,
                "rerank_result": rr,
                "scoring": scoring_result,
                "decision": decision,
                "reasons": reasons,
                "pair_features": pair_features,
            }
        )

    # Sort by final score descending
    scored_candidates.sort(key=lambda x: x["scoring"].final_score, reverse=True)

    # Build result
    best = scored_candidates[0]
    best_c = best["candidate"]
    best_decision = best["decision"]

    best_candidate_dict = {
        "product_id": best_c.product_id,
        "name": best_c.name,
        "article": best_c.article,
        "brand": best_c.brand,
        "category_path": best_c.category_path,
    }

    alternatives = []
    for sc in scored_candidates[:5]:
        c = sc["candidate"]
        alternatives.append(
            {
                "product_id": c.product_id,
                "name": c.name,
                "article": c.article,
                "brand": c.brand,
                "retrieval_rank": c.retrieval_rank,
                "lexical_score": c.lexical_score,
                "semantic_score": c.semantic_score,
                "rerank_score": sc["rerank_result"].rerank_score,
                "rules_score": sc["scoring"].bonus + sc["scoring"].penalty,
                "final_score": sc["scoring"].final_score,
                "reasons": sc["reasons"],
            }
        )

    result_status = best_decision.status
    result_confidence = best_decision.confidence
    result_reasons = best["reasons"].copy()

    # Build decision trace for the best candidate
    best_scoring = best["scoring"]
    best_pf = best["pair_features"]
    decision_trace = {
        "base_score": best_scoring.base_score,
        "bonus": best_scoring.bonus,
        "penalty": best_scoring.penalty,
        "final_score": best_scoring.final_score,
        "short_circuit": best_scoring.short_circuit,
        "auto_match_forbidden": best_scoring.auto_match_forbidden,
        "features": asdict(best_pf),
        "decision": {
            "status": best_decision.status,
            "confidence": best_decision.confidence,
        },
        "candidates_found": len(candidates),
        "candidates_reranked": len(reranked),
    }

    # Trigger Agentic RAG loop if not confident and settings allow it
    if (
        result_status != "auto_match"
        and settings.agentic_resolution_enabled
        and settings.active_llm_api_key
        and settings.active_llm_api_key not in ("", "none")
    ):
        agent_decision = await resolve_agentically(
            raw_text,
            scored_candidates[:5],
            session,
            extracted_attrs=extracted_attrs,
            token_tracker=token_tracker,
        )
        if agent_decision:
            new_status = agent_decision.get("status")
            if new_status == "auto_match":
                # Override the result to auto match
                result_status = "auto_match"
                result_confidence = 0.99

                # Fetch the product from DB if available (or use existing)
                pid = agent_decision.get("product_id")
                # Look for it in alternatives
                matched_alt = next((alt for alt in alternatives if alt["product_id"] == pid), None)
                if matched_alt:
                    best_candidate_dict = {
                        "product_id": matched_alt["product_id"],
                        "name": matched_alt["name"],
                        "article": matched_alt["article"],
                        "brand": matched_alt["brand"],
                        "category_path": "",
                    }
                else:
                    # Agent hallucinated or found something via catalog search not in top 5
                    best_candidate_dict["product_id"] = pid

            result_reasons = [f"Agent Resolution: {agent_decision.get('reasoning')}"]
            decision_trace["agent_resolution"] = agent_decision

    return MatchItemResult(
        request_item_id=request_item_id,
        line_id=line_id,
        raw_text=raw_text,
        normalized_text=normalized_text,
        extracted_attributes=extracted_attrs,
        status=result_status,
        confidence=result_confidence,
        best_candidate=best_candidate_dict,
        alternatives=alternatives,
        reasons=result_reasons,
        decision_trace=decision_trace,
    )
