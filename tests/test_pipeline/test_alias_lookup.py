"""Unit tests for AliasRepo used in the matching pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from matcher.db.repos.alias import AliasRepo


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


def _make_alias(product_id: str, normalized_text: str):
    alias = MagicMock()
    alias.product_id = product_id
    alias.normalized_alias_text = normalized_text
    return alias


class TestAliasRepo:
    @pytest.mark.asyncio
    async def test_find_by_normalized_text_calls_execute(self, mock_session):
        mock_session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
        repo = AliasRepo(mock_session)
        result = await repo.find_by_normalized_text("труба пвх 50 мм")
        mock_session.execute.assert_awaited_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_find_by_normalized_text_returns_aliases(self, mock_session):
        alias1 = _make_alias("prod_001", "труба пвх 50")
        alias2 = _make_alias("prod_002", "труба пвх 50")
        mock_session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[alias1, alias2])))
        )
        repo = AliasRepo(mock_session)
        result = await repo.find_by_normalized_text("труба пвх 50")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_product_ids_by_text_returns_set(self, mock_session):
        alias1 = _make_alias("prod_001", "насос grundfos")
        alias2 = _make_alias("prod_002", "насос grundfos")
        alias3 = _make_alias("prod_001", "насос grundfos")  # duplicate product_id
        mock_session.execute.return_value = MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[alias1, alias2, alias3]))
            )
        )
        repo = AliasRepo(mock_session)
        result = await repo.find_product_ids_by_text("насос grundfos")
        assert isinstance(result, set)
        assert result == {"prod_001", "prod_002"}

    @pytest.mark.asyncio
    async def test_find_product_ids_by_text_empty(self, mock_session):
        mock_session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
        repo = AliasRepo(mock_session)
        result = await repo.find_product_ids_by_text("несуществующий товар")
        assert isinstance(result, set)
        assert len(result) == 0
