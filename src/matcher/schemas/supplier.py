from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SupplierProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: str
    supplier_name: str
    strict_mode: bool
    is_active: bool

class SupplierCreate(BaseModel):
    supplier_id: str = Field(..., min_length=1, max_length=200)
    supplier_name: str = Field(..., min_length=1, max_length=500)
    strict_mode: bool = False

class SupplierUpdate(BaseModel):
    supplier_name: str | None = Field(None, max_length=500)
    strict_mode: bool | None = None
    is_active: bool | None = None


class SupplierMappingInput(BaseModel):
    supplier_sku: str | None = Field(None, max_length=200)
    supplier_article: str | None = Field(None, max_length=200)
    supplier_raw_text: str | None = Field(None, max_length=2000)
    product_id: str = Field(..., max_length=200)
    mapping_type: Literal["exact", "approved", "manual", "learned"] = "approved"
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class SupplierMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mapping_id: str
    supplier_id: str
    supplier_sku: str | None = None
    supplier_article: str | None = None
    supplier_raw_text: str | None = None
    product_id: str
    mapping_type: str
    confidence: float | None = None


class QualityMetrics(BaseModel):
    total_cases: int
    top1_accuracy: float | None = None
    top3_recall: float | None = None
    precision_at_1: float | None = None
    auto_match_false_positive_rate: float | None = None
    review_acceptance_rate: float | None = None
    avg_latency_ms: float | None = None
