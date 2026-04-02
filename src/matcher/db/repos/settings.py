"""Repository for system_settings key-value table."""

from __future__ import annotations

from inspect import isawaitable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, key: str, value: str | None, *, commit: bool = True) -> None:
        """INSERT or UPDATE a setting by key."""
        await self.session.execute(
            text(
                "INSERT INTO system_settings (key, value, updated_at) "
                "VALUES (:key, :value, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = now()"
            ),
            {"key": key, "value": value},
        )
        if commit:
            await self.session.commit()

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Get a single setting value by key."""
        result = await self.session.execute(
            text("SELECT value FROM system_settings WHERE key = :key"),
            {"key": key},
        )
        row = result.first()
        return row[0] if row is not None else default

    async def get_all(self) -> dict[str, str | None]:
        """Return all settings as a {key: value} dict."""
        result = await self.session.execute(text("SELECT key, value FROM system_settings"))
        rows = result.fetchall()
        if isawaitable(rows):
            rows = await rows
        return {row[0]: row[1] for row in rows}
