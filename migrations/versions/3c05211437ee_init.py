"""init

Revision ID: 3c05211437ee
Revises:
Create Date: 2026-03-30 20:12:25.560644
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3c05211437ee"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL_UP = """\
create extension if not exists vector;
create extension if not exists pg_trgm;
create extension if not exists unaccent;

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create table if not exists supplier_profiles (
  supplier_id              text primary key,
  supplier_name            text not null,
  is_active                boolean not null default true,
  strict_mode              boolean not null default false,
  normalization_rules      jsonb not null default '{}'::jsonb,
  notes                    text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create trigger trg_supplier_profiles_updated_at
before update on supplier_profiles
for each row execute function set_updated_at();

create table if not exists catalog_products (
  product_id               text primary key,
  onec_ref                 text unique,
  code                     text,
  article                  text,
  name                     text not null,
  full_name                text,
  normalized_name          text not null,
  normalized_full_name     text,
  brand                    text,
  normalized_brand         text,
  manufacturer             text,
  manufacturer_code        text,
  category_id              text,
  category_path            text,
  unit                     text,
  packaging                text,
  size_value               numeric,
  size_unit                text,
  weight_value             numeric,
  weight_unit              text,
  volume_value             numeric,
  volume_unit              text,
  attributes_json          jsonb not null default '{}'::jsonb,
  search_document          text not null,
  search_tsv               tsvector,
  is_active                boolean not null default true,
  source_hash              text,
  source_version           text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create trigger trg_catalog_products_updated_at
before update on catalog_products
for each row execute function set_updated_at();
create index if not exists idx_catalog_products_article on catalog_products(article);
create index if not exists idx_catalog_products_code on catalog_products(code);
create index if not exists idx_catalog_products_brand on catalog_products(normalized_brand);
create index if not exists idx_catalog_products_category on catalog_products(category_id);
create index if not exists idx_catalog_products_active on catalog_products(is_active);
create index if not exists idx_catalog_products_search_tsv on catalog_products using gin(search_tsv);
create index if not exists idx_catalog_products_name_trgm on catalog_products using gin(normalized_name gin_trgm_ops);
create index if not exists idx_catalog_products_full_name_trgm on catalog_products using gin(normalized_full_name gin_trgm_ops);
create index if not exists idx_catalog_products_search_doc_trgm on catalog_products using gin(search_document gin_trgm_ops);

create table if not exists catalog_embeddings (
  product_id               text primary key references catalog_products(product_id) on delete cascade,
  embedding_model          text not null,
  embedding_version        text not null,
  embedding_vector         vector(1024) not null,
  created_at               timestamptz not null default now()
);
create index if not exists idx_catalog_embeddings_hnsw
on catalog_embeddings using hnsw (embedding_vector vector_cosine_ops);

create table if not exists catalog_aliases (
  alias_id                 text primary key,
  product_id               text not null references catalog_products(product_id) on delete cascade,
  alias_text               text not null,
  normalized_alias_text    text not null,
  alias_type               text not null check (alias_type in ('internal','historical','user_added','supplier_derived')),
  weight                   numeric not null default 1.0,
  created_by               text,
  created_at               timestamptz not null default now()
);
create index if not exists idx_catalog_aliases_product on catalog_aliases(product_id);
create index if not exists idx_catalog_aliases_norm_trgm on catalog_aliases using gin(normalized_alias_text gin_trgm_ops);

create table if not exists supplier_mappings (
  mapping_id               text primary key,
  supplier_id              text not null references supplier_profiles(supplier_id) on delete cascade,
  supplier_sku             text,
  supplier_article         text,
  supplier_raw_text        text,
  normalized_supplier_text text,
  product_id               text not null references catalog_products(product_id) on delete cascade,
  mapping_type             text not null check (mapping_type in ('exact','approved','manual','learned')),
  confidence               numeric,
  approved_by              text,
  approved_at              timestamptz,
  is_active                boolean not null default true,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create trigger trg_supplier_mappings_updated_at
before update on supplier_mappings
for each row execute function set_updated_at();
create index if not exists idx_supplier_mappings_supplier on supplier_mappings(supplier_id);
create index if not exists idx_supplier_mappings_product on supplier_mappings(product_id);
create index if not exists idx_supplier_mappings_supplier_sku on supplier_mappings(supplier_id, supplier_sku);
create index if not exists idx_supplier_mappings_supplier_article on supplier_mappings(supplier_id, supplier_article);
create index if not exists idx_supplier_mappings_norm_text_trgm on supplier_mappings using gin(normalized_supplier_text gin_trgm_ops);

create table if not exists match_requests (
  request_id               text primary key,
  supplier_id              text references supplier_profiles(supplier_id),
  source_type              text not null,
  submitted_by             text,
  file_name                text,
  status                   text not null check (status in ('queued','running','done','failed')),
  total_items              integer not null default 0,
  processed_items          integer not null default 0,
  auto_matched_items       integer not null default 0,
  review_needed_items      integer not null default 0,
  no_match_items           integer not null default 0,
  error_message            text,
  created_at               timestamptz not null default now(),
  started_at               timestamptz,
  finished_at              timestamptz
);
create index if not exists idx_match_requests_status on match_requests(status);
create index if not exists idx_match_requests_supplier on match_requests(supplier_id);
create index if not exists idx_match_requests_created_at on match_requests(created_at desc);

create table if not exists match_request_items (
  request_item_id          text primary key,
  request_id               text not null references match_requests(request_id) on delete cascade,
  line_id                  text,
  raw_text                 text not null,
  normalized_text          text,
  extracted_attributes     jsonb not null default '{}'::jsonb,
  status                   text not null check (status in ('auto_match','review_needed','no_match')),
  best_product_id          text references catalog_products(product_id),
  confidence               numeric,
  reasons_json             jsonb not null default '[]'::jsonb,
  decision_trace_json      jsonb not null default '{}'::jsonb,
  reviewed_by              text,
  reviewed_at              timestamptz,
  final_product_id         text references catalog_products(product_id),
  final_decision           text check (final_decision in ('accepted','corrected','rejected')),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create trigger trg_match_request_items_updated_at
before update on match_request_items
for each row execute function set_updated_at();
create index if not exists idx_match_request_items_request on match_request_items(request_id);
create index if not exists idx_match_request_items_status on match_request_items(status);
create index if not exists idx_match_request_items_best_product on match_request_items(best_product_id);
create index if not exists idx_match_request_items_final_product on match_request_items(final_product_id);

create table if not exists match_candidates (
  candidate_id             text primary key,
  request_item_id          text not null references match_request_items(request_item_id) on delete cascade,
  product_id               text not null references catalog_products(product_id) on delete cascade,
  retrieval_rank           integer not null,
  lexical_score            numeric,
  semantic_score           numeric,
  rerank_score             numeric,
  rules_score              numeric,
  final_score              numeric,
  reasons_json             jsonb not null default '[]'::jsonb,
  created_at               timestamptz not null default now()
);
create index if not exists idx_match_candidates_item on match_candidates(request_item_id);
create index if not exists idx_match_candidates_product on match_candidates(product_id);
create index if not exists idx_match_candidates_item_rank on match_candidates(request_item_id, retrieval_rank);
create index if not exists idx_match_candidates_item_score on match_candidates(request_item_id, final_score desc);

create table if not exists golden_labels (
  label_id                 text primary key,
  raw_query                text not null,
  normalized_query         text not null,
  supplier_id              text references supplier_profiles(supplier_id),
  product_id               text references catalog_products(product_id),
  label_type               text not null check (label_type in ('positive','negative','ambiguous')),
  source                   text not null,
  verified_by              text,
  verified_at              timestamptz,
  created_at               timestamptz not null default now()
);
create index if not exists idx_golden_labels_supplier on golden_labels(supplier_id);
create index if not exists idx_golden_labels_product on golden_labels(product_id);
create index if not exists idx_golden_labels_label_type on golden_labels(label_type);

create table if not exists normalization_synonyms (
  synonym_id               text primary key,
  domain                   text not null,
  supplier_id              text references supplier_profiles(supplier_id),
  category_id              text,
  source_text              text not null,
  normalized_source_text   text not null,
  target_text              text not null,
  target_type              text not null,
  weight                   numeric not null default 1.0,
  is_active                boolean not null default true,
  created_at               timestamptz not null default now()
);
create index if not exists idx_norm_synonyms_domain on normalization_synonyms(domain);
create index if not exists idx_norm_synonyms_supplier on normalization_synonyms(supplier_id);
create index if not exists idx_norm_synonyms_source_trgm on normalization_synonyms using gin(normalized_source_text gin_trgm_ops);

create table if not exists index_versions (
  index_version_id         text primary key,
  embedding_model          text not null,
  embedding_version        text not null,
  lexical_version          text not null,
  rules_version            text not null,
  is_active                boolean not null default false,
  product_count            integer not null default 0,
  created_by               text,
  created_at               timestamptz not null default now(),
  activated_at             timestamptz
);
create unique index if not exists uq_index_versions_active
on index_versions (is_active) where is_active = true;

create table if not exists quality_reports (
  report_id                text primary key,
  index_version_id         text references index_versions(index_version_id),
  scope                    text not null,
  scope_value              text,
  total_cases              integer not null,
  top1_accuracy            numeric,
  top3_recall              numeric,
  precision_at_1           numeric,
  auto_match_fp_rate       numeric,
  review_acceptance_rate   numeric,
  avg_latency_ms           numeric,
  report_json              jsonb not null default '{}'::jsonb,
  created_at               timestamptz not null default now()
);
"""

DDL_DOWN = """\
drop table if exists quality_reports cascade;
drop table if exists index_versions cascade;
drop table if exists normalization_synonyms cascade;
drop table if exists golden_labels cascade;
drop table if exists match_candidates cascade;
drop table if exists match_request_items cascade;
drop table if exists match_requests cascade;
drop table if exists supplier_mappings cascade;
drop table if exists catalog_aliases cascade;
drop table if exists catalog_embeddings cascade;
drop table if exists catalog_products cascade;
drop table if exists supplier_profiles cascade;
drop function if exists set_updated_at();
drop extension if exists unaccent;
drop extension if exists pg_trgm;
drop extension if exists vector;
"""


def upgrade() -> None:
    op.execute(DDL_UP)


def downgrade() -> None:
    op.execute(DDL_DOWN)
