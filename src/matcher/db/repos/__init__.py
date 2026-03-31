from __future__ import annotations

from matcher.db.repos.alias import AliasRepo
from matcher.db.repos.catalog import CatalogRepo
from matcher.db.repos.match import MatchRepo
from matcher.db.repos.metrics import MetricsRepo
from matcher.db.repos.supplier import SupplierRepo
from matcher.db.repos.user import UserRepo

__all__ = [
    "AliasRepo",
    "CatalogRepo",
    "MatchRepo",
    "MetricsRepo",
    "SupplierRepo",
    "UserRepo",
]
