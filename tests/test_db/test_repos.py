from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from matcher.db.models import NormalizationSynonym
from matcher.db.repos.alias import AliasRepo
from matcher.db.repos.audit import AuditRepo
from matcher.db.repos.catalog import CatalogRepo
from matcher.db.repos.metrics import MetricsRepo
from matcher.db.repos.supplier import SupplierRepo
from matcher.db.repos.synonym import SynonymRepo
from matcher.db.repos.token_usage import TokenUsageRepo
from matcher.db.repos.user import UserRepo


class _Scalars:
    def __init__(self, values: list):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(
        self,
        *,
        scalar_value=None,
        scalar_one_or_none_value=None,
        scalar_values: list | None = None,
        rows: list | None = None,
        rowcount: int = 0,
    ) -> None:
        self._scalar_value = scalar_value
        self._scalar_one_or_none_value = scalar_one_or_none_value
        self._scalar_values = scalar_values or []
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalar_one_or_none_value

    def scalars(self):
        return _Scalars(self._scalar_values)

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.execute = AsyncMock(side_effect=self._execute)
        self.flush = AsyncMock()
        self.add = MagicMock()
        self.delete = AsyncMock()

    async def _execute(self, _statement):
        if not self.results:
            raise AssertionError("No fake result queued")
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_user_repo_reads_lists_creates_and_updates_user():
    existing = SimpleNamespace(user_id="usr_1", username="old")
    users = [existing, SimpleNamespace(user_id="usr_2", username="second")]
    session = _Session(
        _Result(scalar_one_or_none_value=existing),
        _Result(scalar_one_or_none_value=existing),
        _Result(scalar_values=users),
        _Result(scalar_one_or_none_value=existing),
        _Result(scalar_one_or_none_value=None),
    )
    repo = UserRepo(session)

    assert await repo.get_by_username("old") is existing
    assert await repo.get_by_id("usr_1") is existing
    assert await repo.list_users() == users

    created = await repo.create_user("new", "hash", full_name="New User", role="admin")
    assert created.user_id.startswith("usr_")
    assert created.username == "new"
    assert created.role == "admin"
    session.add.assert_called_once_with(created)
    assert session.flush.await_count == 1

    updated = await repo.update_user("usr_1", username="new-name", ignored_field="ignored")
    assert updated is existing
    assert existing.username == "new-name"
    assert not hasattr(existing, "ignored_field")
    assert await repo.update_user("missing", username="nope") is None


@pytest.mark.asyncio
async def test_supplier_repo_crud_and_mapping_lookup_paths():
    supplier = SimpleNamespace(supplier_id="sup_1", supplier_name="Old", strict_mode=False)
    mapping = SimpleNamespace(mapping_id="map_1", product_id="prod_1")
    suppliers = [supplier]
    mappings = [mapping]
    session = _Session(
        _Result(scalar_values=suppliers),
        _Result(scalar_one_or_none_value=supplier),
        _Result(scalar_one_or_none_value=supplier),
        _Result(scalar_one_or_none_value=mapping),
        _Result(scalar_one_or_none_value=mapping),
        _Result(scalar_one_or_none_value=mapping),
        _Result(rowcount=1),
        _Result(scalar_values=mappings),
    )
    repo = SupplierRepo(session)

    assert await repo.list_suppliers() == suppliers
    assert await repo.get_supplier("sup_1") is supplier

    created = await repo.create_supplier("sup_new", "New Supplier", strict_mode=True)
    assert created.supplier_id == "sup_new"
    assert created.strict_mode is True
    session.add.assert_called_once_with(created)

    updated = await repo.update_supplier("sup_1", supplier_name="New Name", unknown="ignored")
    assert updated is supplier
    assert supplier.supplier_name == "New Name"
    assert not hasattr(supplier, "unknown")

    created_mapping = await repo.create_mapping("sup_1", {"product_id": "prod_1"})
    assert created_mapping.mapping_id.startswith("map_")
    assert created_mapping.product_id == "prod_1"

    assert await repo.find_mapping("sup_1", article="A-1") is mapping
    assert await repo.find_mapping("sup_1", normalized_text="cement") is mapping
    assert await repo.find_mapping("sup_1", raw_text="Цемент") is mapping
    assert await repo.find_mapping("sup_1") is None
    assert await repo.delete_supplier("sup_1") is True
    assert await repo.get_supplier_mappings("sup_1") == mappings


@pytest.mark.asyncio
async def test_supplier_update_returns_none_when_missing():
    session = _Session(_Result(scalar_one_or_none_value=None))

    assert await SupplierRepo(session).update_supplier("missing", supplier_name="x") is None


@pytest.mark.asyncio
async def test_audit_repo_logs_and_lists_entries():
    entry = SimpleNamespace(log_id="audit_1")
    rows = [entry]
    session = _Session(_Result(scalar_value=3), _Result(scalar_values=rows))
    repo = AuditRepo(session)

    created = await repo.log(
        action="approve",
        entity_type="match",
        entity_id="item_1",
        user_id="usr_1",
        username="operator",
        details={"from": "review"},
        ip_address="127.0.0.1",
    )
    assert created.log_id.startswith("audit_")
    assert created.details == {"from": "review"}
    session.add.assert_called_once_with(created)

    listed, total = await repo.list_logs(
        entity_type="match",
        entity_id="item_1",
        user_id="usr_1",
        action="approve",
    )

    assert listed == rows
    assert total == 3


@pytest.mark.asyncio
async def test_alias_repo_returns_aliases_and_product_ids():
    aliases = [
        SimpleNamespace(product_id="prod_1"),
        SimpleNamespace(product_id="prod_2"),
        SimpleNamespace(product_id="prod_1"),
    ]
    session = _Session(_Result(scalar_values=aliases), _Result(scalar_values=aliases))
    repo = AliasRepo(session)

    assert await repo.find_by_normalized_text("alias") == aliases
    assert await repo.find_product_ids_by_text("alias") == {"prod_1", "prod_2"}


@pytest.mark.asyncio
async def test_synonym_repo_finds_and_merges_supplier_overrides(monkeypatch: pytest.MonkeyPatch):
    session = _Session(
        _Result(scalar_values=[SimpleNamespace(target_text="target")]),
        _Result(scalar_values=[SimpleNamespace(target_text="supplier category target")]),
    )
    repo = SynonymRepo(session)

    assert [s.target_text for s in await repo.find_synonyms(domain="units")] == ["target"]
    assert [
        s.target_text for s in await repo.find_synonyms(supplier_id="sup_1", category_id="cat_1")
    ] == ["supplier category target"]

    global_syn = NormalizationSynonym(
        normalized_source_text="цемент",
        target_text="cement",
    )
    supplier_syn = NormalizationSynonym(
        normalized_source_text="цемент",
        target_text="supplier cement",
    )
    calls: list[str | None] = []

    async def fake_find_synonyms(supplier_id=None, **_kwargs):
        calls.append(supplier_id)
        return [global_syn] if supplier_id is None else [supplier_syn]

    monkeypatch.setattr(repo, "find_synonyms", fake_find_synonyms)

    assert await repo.build_synonym_map(supplier_id="sup_1") == {"цемент": "supplier cement"}
    assert calls == [None, "sup_1"]


@pytest.mark.asyncio
async def test_token_usage_repo_formats_summary():
    totals = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        total_cost_usd=0.25,
        api_calls=2,
    )
    provider_row = SimpleNamespace(provider="openai", total_tokens=15, cost_usd=0.25, calls=2)
    model_row = SimpleNamespace(
        provider="openai",
        model="gpt",
        operation="chat",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.25,
        calls=2,
    )
    daily_row = SimpleNamespace(date="2026-05-31", total_tokens=15, cost_usd=0.25)
    session = _Session(
        _Result(rows=[totals]),
        _Result(rows=[provider_row]),
        _Result(rows=[model_row]),
        _Result(rows=[daily_row]),
    )

    summary = await TokenUsageRepo(session).get_summary(days=7, provider="openai")

    assert summary == {
        "period_days": 7,
        "totals": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "total_cost_usd": 0.25,
            "api_calls": 2,
        },
        "by_provider": [
            {
                "provider": "openai",
                "total_tokens": 15,
                "cost_usd": 0.25,
                "calls": 2,
            }
        ],
        "by_model": [
            {
                "provider": "openai",
                "model": "gpt",
                "operation": "chat",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost_usd": 0.25,
                "calls": 2,
            }
        ],
        "daily": [
            {
                "date": "2026-05-31",
                "total_tokens": 15,
                "cost_usd": 0.25,
            }
        ],
    }


@pytest.mark.asyncio
async def test_catalog_repo_read_search_count_and_bulk_upsert():
    product = SimpleNamespace(product_id="prod_1")
    products = [product, SimpleNamespace(product_id="prod_2")]
    session = _Session(
        _Result(scalar_one_or_none_value=product),
        _Result(scalar_values=products),
        _Result(scalar_values=products),
        _Result(rowcount=2),
        _Result(scalar_value=7),
    )
    repo = CatalogRepo(session)

    assert await repo.get_product("prod_1") is product
    assert await repo.search_products(limit=10) == products
    assert await repo.search_products(query="pump", limit=10) == products
    assert await repo.upsert_products([]) == 0
    assert await repo.upsert_products([{"product_id": "prod_1", "name": "Pump"}]) == 2
    assert await repo.count_active() == 7


@pytest.mark.asyncio
async def test_catalog_repo_embedding_alias_delete_and_index_paths():
    product = SimpleNamespace(product_id="prod_1")
    versions = [SimpleNamespace(index_version_id="idx_1")]
    session = _Session(
        _Result(scalar_values=[product]),
        _Result(),
        _Result(scalar_one_or_none_value=product),
        _Result(scalar_one_or_none_value=None),
        _Result(),
        _Result(scalar_values=versions),
        _Result(scalar_one_or_none_value=None),
        _Result(scalar_one_or_none_value=versions[0]),
        _Result(),
        _Result(),
    )
    repo = CatalogRepo(session)

    assert await repo.get_products_needing_embedding("model", "v1") == [product]

    await repo.upsert_embedding("prod_1", "model", "v1", [0.1, 0.2])
    assert session.execute.await_count == 2

    alias = await repo.create_alias(
        "prod_1",
        "Supplier Pump",
        "supplier pump",
        alias_type="imported",
        created_by="tester",
    )
    assert alias.alias_id.startswith("alias_")
    assert alias.product_id == "prod_1"
    assert alias.alias_type == "imported"
    session.add.assert_called_once_with(alias)

    assert await repo.delete_product("prod_1") is True
    session.delete.assert_awaited_once_with(product)
    assert await repo.delete_product("missing") is False

    assert await repo.delete_all_products() == 1
    assert await repo.list_index_versions() == versions
    assert await repo.activate_index_version("missing") is False
    assert await repo.activate_index_version("idx_1") is True


@pytest.mark.asyncio
async def test_catalog_repo_count_active_returns_zero_when_scalar_is_none():
    session = _Session(_Result(scalar_value=None))

    assert await CatalogRepo(session).count_active() == 0


@pytest.mark.asyncio
async def test_metrics_repo_returns_empty_metrics_when_no_reviewed_cases():
    session = _Session(_Result(scalar_value=0))

    assert await MetricsRepo(session).compute_quality_metrics(supplier_id="sup_1") == {
        "total_cases": 0,
        "top1_accuracy": None,
        "top3_recall": None,
        "precision_at_1": None,
        "auto_match_false_positive_rate": None,
        "review_acceptance_rate": None,
        "avg_latency_ms": None,
    }


@pytest.mark.asyncio
async def test_metrics_repo_computes_quality_metrics():
    session = _Session(
        _Result(scalar_value=10),
        _Result(scalar_value=7),
        _Result(scalar_value=5),
        _Result(scalar_value=1),
        _Result(scalar_value=1234.56),
    )

    metrics = await MetricsRepo(session).compute_quality_metrics(supplier_id="sup_1")

    assert metrics == {
        "total_cases": 10,
        "top1_accuracy": 0.7,
        "top3_recall": None,
        "precision_at_1": 1.4,
        "auto_match_false_positive_rate": 0.2,
        "auto_match_fp_rate": 0.2,
        "review_acceptance_rate": 0.7,
        "avg_latency_ms": 1234.6,
    }


@pytest.mark.asyncio
async def test_metrics_repo_handles_missing_auto_matches_and_latency():
    session = _Session(
        _Result(scalar_value=3),
        _Result(scalar_value=1),
        _Result(scalar_value=0),
        _Result(scalar_value=0),
        _Result(scalar_value=None),
    )

    metrics = await MetricsRepo(session).compute_quality_metrics()

    assert metrics["total_cases"] == 3
    assert metrics["top1_accuracy"] == 0.3333
    assert metrics["precision_at_1"] is None
    assert metrics["auto_match_false_positive_rate"] is None
    assert metrics["auto_match_fp_rate"] is None
    assert metrics["review_acceptance_rate"] == 0.3333
    assert metrics["avg_latency_ms"] is None


@pytest.mark.asyncio
async def test_metrics_repo_saves_quality_report():
    session = _Session()
    report = await MetricsRepo(session).save_quality_report(
        {
            "scope": "global",
            "scope_value": None,
            "total_cases": 10,
            "top1_accuracy": 0.9,
            "report_json": {"sample": True},
        }
    )

    assert report.report_id.startswith("report_")
    assert report.scope == "global"
    assert report.total_cases == 10
    session.add.assert_called_once_with(report)
    session.flush.assert_awaited_once()
