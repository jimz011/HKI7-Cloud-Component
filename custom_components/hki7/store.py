"""Persistent storage for HKI 7 Cloud.

A thin async wrapper over Home Assistant's `Store` helper. Everything lives in a
single JSON document under `.storage/hki7_cloud`, namespaced by section so later
phases (shared dashboards, parental-control policies, family config) can slot in
without a schema migration.

Phase 1 uses only the ``backups`` section:

    {
      "backups": {
        "<ha_user_id>": [
          {"id": str, "created": iso8601, "label": str, "size": int, "payload": <json>},
          ...  # newest first, capped at MAX_BACKUPS
        ]
      }
    }
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import MAX_BACKUPS, STORAGE_KEY, STORAGE_VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Hki7Store:
    """Serialises all reads/writes through a single HA Store document."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def _load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = await self._store.async_load() or {}
            self._data.setdefault("backups", {})
        return self._data

    async def _save(self) -> None:
        await self._store.async_save(self._data or {})

    # ── Backups (Phase 1) ────────────────────────────────────────────────

    async def put_backup(
        self, user_id: str, payload: Any, label: str | None = None
    ) -> dict[str, Any]:
        """Store a backup for ``user_id`` and return its metadata (no payload)."""
        data = await self._load()
        backups: list[dict[str, Any]] = data["backups"].setdefault(user_id, [])
        entry = {
            "id": uuid.uuid4().hex,
            "created": _now_iso(),
            "label": label or "",
            "size": len(str(payload)),
            "payload": payload,
        }
        backups.insert(0, entry)
        # Keep newest MAX_BACKUPS, drop the rest.
        del backups[MAX_BACKUPS:]
        await self._save()
        return _meta(entry)

    async def list_backups(self, user_id: str) -> list[dict[str, Any]]:
        """Return backup metadata (no payloads) for ``user_id``, newest first."""
        data = await self._load()
        return [_meta(e) for e in data["backups"].get(user_id, [])]

    async def get_backup(self, user_id: str, backup_id: str) -> Any | None:
        """Return the payload of one backup owned by ``user_id``, or None."""
        data = await self._load()
        for entry in data["backups"].get(user_id, []):
            if entry["id"] == backup_id:
                return entry["payload"]
        return None


def _meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the payload from a backup entry for list/put responses."""
    return {k: v for k, v in entry.items() if k != "payload"}
