from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchItemInput(BaseModel):
    line_id: str | None = None
    raw_text: str = Field(..., min_length=1, max_length=2000)
    original_row: dict[str, Any] | None = None
    hints: dict[str, Any] | None = None


class MatchRequestInput(BaseModel):
    supplier_id: str | None = None
    source_type: str = "api"
    submitted_by: str | None = None
    items: list[MatchItemInput] = Field(..., min_length=1, max_length=5000)


class ProductRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    name: str
    article: str | None = None
    brand: str | None = None
    category_path: str | None = None


class Candidate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    name: str
    article: str | None = None
    brand: str | None = None
    retrieval_rank: int
    lexical_score: float | None = None
    semantic_score: float | None = None
    rerank_score: float | None = None
    rules_score: float | None = None
    final_score: float | None = None
    reasons: list[str] = []


class MatchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_item_id: str
    line_id: str | None = None
    raw_text: str
    original_row: dict[str, Any] | None = None
    normalized_text: str | None = None
    extracted_attributes: dict[str, Any] = {}
    status: Literal["auto_match", "review_needed", "no_match"]
    confidence: float | None = None
    best_candidate: ProductRef | None = None
    alternatives: list[Candidate] = []
    reasons: list[str] = []


class MatchResponse(BaseModel):
    request_id: str
    status: str = "done"
    results: list[MatchResult] = []


class BatchRequestAccepted(BaseModel):
    request_id: str
    status: str = "queued"


class MatchRequestDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    supplier_id: str | None = None
    status: Literal["queued", "running", "done", "failed"]
    total_items: int = 0
    processed_items: int = 0
    auto_matched_items: int = 0
    review_needed_items: int = 0
    no_match_items: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    results: list[MatchResult] | None = None


class MatchItemsPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[MatchResult] = []
