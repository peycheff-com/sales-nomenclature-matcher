from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CatalogImportInput(BaseModel):
    source_type: Literal["onec_api", "csv", "xlsx"]
    source_version: str | None = Field(None, max_length=200)
    file_url: str | None = Field(None, max_length=2000)
    dry_run: bool = False


class CatalogReindexInput(BaseModel):
    embedding_model: str | None = None
    embedding_version: str | None = None
    lexical_version: str | None = None
    rules_version: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"
