from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    supplier_id: Mapped[str] = mapped_column(Text, primary_key=True)
    supplier_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    strict_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    normalization_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    mappings: Mapped[list[SupplierMapping]] = relationship(back_populates="supplier")


class CatalogProduct(Base):
    __tablename__ = "catalog_products"

    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    onec_ref: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    article: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    packaging: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    size_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    search_document: Mapped[str] = mapped_column(Text, nullable=False)
    search_tsv = Column(TSVECTOR)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    source_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    embedding: Mapped[CatalogEmbedding | None] = relationship(back_populates="product")
    aliases: Mapped[list[CatalogAlias]] = relationship(back_populates="product")


class CatalogEmbedding(Base):
    __tablename__ = "catalog_embeddings"

    product_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_products.product_id", ondelete="CASCADE"), primary_key=True
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_version: Mapped[str] = mapped_column(Text, nullable=False)
    # NOTE: dimension must match settings.embedding_dimensions. Changing the
    # setting requires a migration to ALTER this column's vector dimension.
    embedding_vector = Column(Vector(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    product: Mapped[CatalogProduct] = relationship(back_populates="embedding")


class CatalogAlias(Base):
    __tablename__ = "catalog_aliases"
    __table_args__ = (
        CheckConstraint(
            "alias_type in ('internal','historical','user_added','supplier_derived')",
            name="ck_catalog_aliases_type",
        ),
    )

    alias_id: Mapped[str] = mapped_column(Text, primary_key=True)
    product_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_products.product_id", ondelete="CASCADE"), nullable=False
    )
    alias_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias_text: Mapped[str] = mapped_column(Text, nullable=False)
    alias_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default="1.0")
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    product: Mapped[CatalogProduct] = relationship(back_populates="aliases")


class SupplierMapping(Base):
    __tablename__ = "supplier_mappings"
    __table_args__ = (
        CheckConstraint(
            "mapping_type in ('exact','approved','manual','learned')",
            name="ck_supplier_mappings_type",
        ),
    )

    mapping_id: Mapped[str] = mapped_column(Text, primary_key=True)
    supplier_id: Mapped[str] = mapped_column(
        Text, ForeignKey("supplier_profiles.supplier_id", ondelete="CASCADE"), nullable=False
    )
    supplier_sku: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_article: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_supplier_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_products.product_id", ondelete="CASCADE"), nullable=False
    )
    mapping_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    supplier: Mapped[SupplierProfile] = relationship(back_populates="mappings")


class MatchRequest(Base):
    __tablename__ = "match_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','queued','running','done','failed')",
            name="ck_match_requests_status",
        ),
    )

    request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    supplier_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("supplier_profiles.supplier_id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="batch_match")
    job_payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    auto_matched_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_needed_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    no_match_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[MatchRequestItem]] = relationship(back_populates="request")


class MatchRequestItem(Base):
    __tablename__ = "match_request_items"
    __table_args__ = (
        CheckConstraint(
            "status in ('auto_match','review_needed','no_match')",
            name="ck_match_request_items_status",
        ),
        CheckConstraint(
            "final_decision in ('accepted','corrected','rejected')",
            name="ck_match_request_items_decision",
        ),
    )

    request_item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("match_requests.request_id", ondelete="CASCADE"), nullable=False
    )
    line_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_row_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extracted_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    best_product_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("catalog_products.product_id"), nullable=True
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    reasons_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    decision_trace_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    final_product_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("catalog_products.product_id"), nullable=True
    )
    final_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    request: Mapped[MatchRequest] = relationship(back_populates="items")
    candidates: Mapped[list[MatchCandidate]] = relationship(back_populates="request_item")


class MatchCandidate(Base):
    __tablename__ = "match_candidates"

    candidate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_item_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("match_request_items.request_item_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_products.product_id", ondelete="CASCADE"), nullable=False
    )
    retrieval_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    lexical_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    semantic_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    rerank_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    rules_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    final_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    reasons_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    request_item: Mapped[MatchRequestItem] = relationship(back_populates="candidates")


class GoldenLabel(Base):
    __tablename__ = "golden_labels"
    __table_args__ = (
        CheckConstraint(
            "label_type in ('positive','negative','ambiguous')",
            name="ck_golden_labels_type",
        ),
    )

    label_id: Mapped[str] = mapped_column(Text, primary_key=True)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("supplier_profiles.supplier_id"), nullable=True
    )
    product_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("catalog_products.product_id"), nullable=True
    )
    label_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id: Mapped[str] = mapped_column(Text, primary_key=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NormalizationSynonym(Base):
    __tablename__ = "normalization_synonyms"

    synonym_id: Mapped[str] = mapped_column(Text, primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("supplier_profiles.supplier_id"), nullable=True
    )
    category_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IndexVersion(Base):
    __tablename__ = "index_versions"

    index_version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_version: Mapped[str] = mapped_column(Text, nullable=False)
    lexical_version: Mapped[str] = mapped_column(Text, nullable=False)
    rules_version: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class QualityReport(Base):
    __tablename__ = "quality_reports"

    report_id: Mapped[str] = mapped_column(Text, primary_key=True)
    index_version_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("index_versions.index_version_id"), nullable=True
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    top1_accuracy: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    top3_recall: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    precision_at_1: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    auto_match_fp_rate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    review_acceptance_rate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    avg_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TokenUsageLog(Base):
    """Tracks token consumption per API call for cost estimation and monitoring."""

    __tablename__ = "token_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("match_requests.request_id", ondelete="SET NULL"), index=True
    )
    operation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="embed | rerank | llm_rerank | agent",
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
