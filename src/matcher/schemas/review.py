from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewInput(BaseModel):
    final_decision: Literal["accepted", "corrected", "rejected"]
    final_product_id: str | None = Field(None, max_length=200)
    comment: str | None = Field(None, max_length=2000)
    create_alias: bool = False
    create_supplier_mapping: bool = False


class ReviewResult(BaseModel):
    ok: bool
    request_item_id: str
