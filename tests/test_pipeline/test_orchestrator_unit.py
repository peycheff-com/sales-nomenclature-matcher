from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from matcher.indexing.search import SearchCandidate
from matcher.pipeline import orchestrator
from matcher.pipeline.decision import MatchDecision
from matcher.pipeline.reranker import RerankResult
from matcher.pipeline.scoring import PairFeatures, ScoringResult


class _Features:
    brand = "brand"
    article = "A-1"
    numbers = [25.0]
    unit = "pcs"
    packaging = None

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "article": self.article,
            "numbers": self.numbers,
            "unit": self.unit,
            "packaging": self.packaging,
        }


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(text="normalized pump")


def _candidate(product_id: str = "p1") -> SearchCandidate:
    return SearchCandidate(
        product_id=product_id,
        name="Pump 25",
        normalized_name="pump 25",
        article="A-1",
        brand="Brand",
        normalized_brand="brand",
        manufacturer_code="M-1",
        category_path="Root / Pumps",
        unit="pcs",
        lexical_score=0.7,
        semantic_score=0.8,
        retrieval_rank=1,
    )


def _patch_scoring_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidate: SearchCandidate | None = None,
    status: str = "review_needed",
    confidence: float = 0.8,
) -> SearchCandidate:
    candidate = candidate or _candidate()
    alias_repo = MagicMock()
    alias_repo.find_product_ids_by_text = AsyncMock(return_value=["p1"])
    monkeypatch.setattr(orchestrator, "AliasRepo", lambda _session: alias_repo)
    monkeypatch.setattr(orchestrator, "hybrid_search", AsyncMock(return_value=[candidate]))
    monkeypatch.setattr(
        orchestrator,
        "rerank_candidates",
        AsyncMock(return_value=[RerankResult(candidate=candidate, rerank_score=0.9)]),
    )
    pair_features = PairFeatures(rerank_score=0.9, alias_hit=1.0)
    monkeypatch.setattr(orchestrator, "compute_pair_features", lambda **_kwargs: pair_features)
    monkeypatch.setattr(orchestrator, "compute_attribute_overlap", lambda *_args: 0.5)
    monkeypatch.setattr(orchestrator, "extract_numbers_from_text", lambda _text: [25.0])
    monkeypatch.setattr(
        orchestrator,
        "score_candidate",
        lambda _features: ScoringResult(
            base_score=0.7,
            bonus=0.1,
            penalty=0.0,
            final_score=confidence,
            features=pair_features,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "decide",
        lambda *_args, **_kwargs: MatchDecision(status=status, confidence=confidence),
    )
    monkeypatch.setattr(orchestrator, "build_reasons", lambda *_args: ["scored"])
    return candidate


@pytest.fixture(autouse=True)
def common_patches(monkeypatch: pytest.MonkeyPatch):
    supplier_repo = MagicMock()
    supplier_repo.get_supplier = AsyncMock(return_value=None)
    monkeypatch.setattr(orchestrator, "SupplierRepo", lambda _session: supplier_repo)
    monkeypatch.setattr(orchestrator, "extract_features", lambda _ctx: _Features())
    monkeypatch.setattr(orchestrator, "check_supplier_override", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator.settings, "llm_matcher_enabled", False)
    monkeypatch.setattr(orchestrator.settings, "agentic_resolution_enabled", False)
    monkeypatch.setattr(
        type(orchestrator.settings),
        "active_llm_api_key",
        property(lambda _self: "none"),
    )


@pytest.mark.asyncio
async def test_match_single_short_circuits_exact_supplier_override(monkeypatch: pytest.MonkeyPatch):
    async def slow_embed(*_args, **_kwargs):
        await orchestrator.asyncio.sleep(10)
        return [0.1]

    monkeypatch.setattr(orchestrator, "embed_single", slow_embed)
    monkeypatch.setattr(
        orchestrator,
        "check_supplier_override",
        AsyncMock(return_value=SimpleNamespace(mapping_type="exact", product_id="p1")),
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        line_id="1",
        supplier_id="s1",
        pre_normalized_ctx=_ctx(),
    )

    assert result.status == "auto_match"
    assert result.confidence == 0.995
    assert result.best_candidate == {"product_id": "p1"}
    assert result.decision_trace == {
        "short_circuit": "supplier_override",
        "mapping_type": "exact",
    }


@pytest.mark.asyncio
async def test_match_single_returns_no_match_when_retrieval_has_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(orchestrator, "hybrid_search", AsyncMock(return_value=[]))

    result = await orchestrator.match_single(
        raw_text="Unknown",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "no_match"
    assert result.confidence == 0.0
    assert result.reasons == ["Кандидаты не найдены"]
    assert result.decision_trace == {"stage": "retrieval", "candidates_found": 0}


@pytest.mark.asyncio
async def test_match_single_uses_agent_when_no_candidates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(orchestrator.settings, "agentic_resolution_enabled", True)
    monkeypatch.setattr(
        type(orchestrator.settings),
        "active_llm_api_key",
        property(lambda _self: "key"),
    )
    monkeypatch.setattr(orchestrator, "hybrid_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        orchestrator,
        "resolve_agentically",
        AsyncMock(return_value={"product_id": "p1", "reasoning": "same family"}),
    )

    result = await orchestrator.match_single(
        raw_text="Unknown",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "review_needed"
    assert result.confidence == 0.80
    assert result.best_candidate == {"product_id": "p1"}
    assert result.decision_trace["stage"] == "agent_fallback"


@pytest.mark.asyncio
async def test_match_single_uses_precomputed_llm_matcher_result(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(orchestrator.settings, "llm_matcher_enabled", True)
    monkeypatch.setattr(orchestrator, "get_cached_catalog", AsyncMock(return_value=[_candidate()]))
    llm_result = SimpleNamespace(
        product_id="p1",
        confidence=0.94,
        reasoning="LLM says same",
        alternatives=[{"product_id": "p1", "confidence": 0.88, "reasoning": "alt"}],
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
        pre_llm_result=llm_result,
    )

    assert result.status == "auto_match"
    assert result.best_candidate == {
        "product_id": "p1",
        "name": "Pump 25",
        "article": "A-1",
        "brand": "Brand",
        "category_path": "Root / Pumps",
    }
    assert result.alternatives[0]["final_score"] == 0.88
    assert result.decision_trace["stage"] == "llm_matcher"
    assert result.reasons == ["LLM Matcher: LLM says same"]


@pytest.mark.asyncio
async def test_match_single_llm_matcher_keeps_unknown_product_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(orchestrator.settings, "llm_matcher_enabled", True)
    monkeypatch.setattr(orchestrator, "get_cached_catalog", AsyncMock(return_value=[_candidate()]))
    llm_result = SimpleNamespace(
        product_id="missing",
        confidence=0.76,
        reasoning="unknown id",
        alternatives=[],
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=[0.1],
        pre_llm_result=llm_result,
    )

    assert result.best_candidate is None
    assert result.status == "review_needed"


@pytest.mark.asyncio
async def test_match_single_scores_reranked_candidates(monkeypatch: pytest.MonkeyPatch):
    _patch_scoring_pipeline(monkeypatch)

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "review_needed"
    assert result.confidence == 0.8
    assert result.best_candidate["product_id"] == "p1"
    assert result.alternatives[0]["rerank_score"] == 0.9
    assert result.alternatives[0]["rules_score"] == 0.1
    assert result.decision_trace["features"]["attribute_overlap_score"] == 0.5


@pytest.mark.asyncio
async def test_match_single_normalizes_applies_synonyms_and_handles_embedding_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_scoring_pipeline(monkeypatch)
    monkeypatch.setattr(orchestrator, "run_pipeline", lambda _raw_text: _ctx())
    synonym_ctx = SimpleNamespace(text="synonym normalized pump")
    apply_synonyms = AsyncMock(return_value=synonym_ctx)
    monkeypatch.setattr(orchestrator, "apply_db_synonyms", apply_synonyms)
    monkeypatch.setattr(orchestrator, "SynonymRepo", lambda _session: object())
    monkeypatch.setattr(orchestrator, "embed_single", AsyncMock(side_effect=RuntimeError("down")))

    result = await orchestrator.match_single(raw_text="Pump", session=object())

    assert result.normalized_text == "synonym normalized pump"
    assert result.status == "review_needed"
    apply_synonyms.assert_awaited_once()
    orchestrator.hybrid_search.assert_awaited_once()
    assert orchestrator.hybrid_search.await_args.kwargs["query_embedding"] is None


@pytest.mark.asyncio
async def test_match_single_uses_supplier_strict_mode_and_thresholds(
    monkeypatch: pytest.MonkeyPatch,
):
    supplier = SimpleNamespace(strict_mode=True, normalization_rules={"thresholds": {"auto": 0.99}})
    supplier_repo = MagicMock()
    supplier_repo.get_supplier = AsyncMock(return_value=supplier)
    monkeypatch.setattr(orchestrator, "SupplierRepo", lambda _session: supplier_repo)
    _patch_scoring_pipeline(monkeypatch)
    captured = {}

    def decide_stub(*_args, **kwargs):
        captured.update(kwargs)
        return MatchDecision(status="review_needed", confidence=0.8)

    monkeypatch.setattr(orchestrator, "decide", decide_stub)

    await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        supplier_id="s1",
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert captured["strict_mode"] is True
    assert captured["supplier_thresholds"] == {"auto": 0.99}


@pytest.mark.asyncio
async def test_match_single_llm_matcher_fetches_small_catalog_and_matches_partial_id(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(orchestrator.settings, "llm_matcher_enabled", True)
    monkeypatch.setattr(orchestrator, "get_catalog_count", AsyncMock(return_value=1))
    monkeypatch.setattr(
        orchestrator,
        "get_cached_catalog",
        AsyncMock(return_value=[_candidate("prd_123")]),
    )
    llm_result = SimpleNamespace(
        product_id="123",
        confidence=0.91,
        reasoning="prefix omitted",
        alternatives=[{"product_id": "missing", "confidence": 0.2, "reasoning": "weak"}],
    )
    monkeypatch.setattr(orchestrator, "llm_match", AsyncMock(return_value=llm_result))

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.best_candidate["product_id"] == "prd_123"
    assert result.alternatives[0]["name"] == ""
    assert result.decision_trace["candidates_shown"] == 1


@pytest.mark.asyncio
async def test_match_single_llm_matcher_reuses_hybrid_candidates_on_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(orchestrator.settings, "llm_matcher_enabled", True)
    monkeypatch.setattr(orchestrator.settings, "small_catalog_threshold", 1)
    monkeypatch.setattr(orchestrator, "get_catalog_count", AsyncMock(return_value=10))
    candidate = _patch_scoring_pipeline(monkeypatch)
    monkeypatch.setattr(orchestrator, "llm_match", AsyncMock(return_value=None))

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.best_candidate["product_id"] == candidate.product_id
    assert orchestrator.hybrid_search.await_count == 1


@pytest.mark.asyncio
async def test_match_single_agent_resolution_promotes_matched_alternative(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_scoring_pipeline(monkeypatch)
    monkeypatch.setattr(orchestrator.settings, "agentic_resolution_enabled", True)
    monkeypatch.setattr(
        type(orchestrator.settings),
        "active_llm_api_key",
        property(lambda _self: "key"),
    )
    monkeypatch.setattr(
        orchestrator,
        "resolve_agentically",
        AsyncMock(
            return_value={"status": "auto_match", "product_id": "p1", "reasoning": "certain"}
        ),
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "auto_match"
    assert result.confidence == 0.99
    assert result.best_candidate == {
        "product_id": "p1",
        "name": "Pump 25",
        "article": "A-1",
        "brand": "Brand",
        "category_path": "",
    }
    assert result.reasons == ["Agent Resolution: certain"]


@pytest.mark.asyncio
async def test_match_single_agent_resolution_keeps_review_status_for_unknown_product(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_scoring_pipeline(monkeypatch)
    monkeypatch.setattr(orchestrator.settings, "agentic_resolution_enabled", True)
    monkeypatch.setattr(
        type(orchestrator.settings),
        "active_llm_api_key",
        property(lambda _self: "key"),
    )
    monkeypatch.setattr(
        orchestrator,
        "resolve_agentically",
        AsyncMock(
            return_value={"status": "review_needed", "product_id": "p2", "reasoning": "maybe"}
        ),
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "review_needed"
    assert result.best_candidate["product_id"] == "p1"
    assert result.decision_trace["agent_resolution"]["product_id"] == "p2"


@pytest.mark.asyncio
async def test_match_single_agent_resolution_auto_match_unknown_product(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_scoring_pipeline(monkeypatch)
    monkeypatch.setattr(orchestrator.settings, "agentic_resolution_enabled", True)
    monkeypatch.setattr(
        type(orchestrator.settings),
        "active_llm_api_key",
        property(lambda _self: "key"),
    )
    monkeypatch.setattr(
        orchestrator,
        "resolve_agentically",
        AsyncMock(return_value={"status": "auto_match", "product_id": "p2", "reasoning": "found"}),
    )

    result = await orchestrator.match_single(
        raw_text="Pump",
        session=object(),
        pre_normalized_ctx=_ctx(),
        query_embedding=None,
    )

    assert result.status == "auto_match"
    assert result.best_candidate["product_id"] == "p2"
