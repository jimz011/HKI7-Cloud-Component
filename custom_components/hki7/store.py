"""Persistent storage for HKI 7 Cloud.

A thin async wrapper over Home Assistant's `Store` helper. Everything lives in a
single JSON document under `.storage/hki7_cloud`, namespaced by section so later
phases (shared dashboards, parental-control policies, family config) can slot in
without a schema migration.

Sections:

    {
      "backups": {
        "<ha_user_id>": [
          {"id": str, "created": iso8601, "label": str, "size": int, "payload": <json>},
          ...  # newest first, capped at MAX_BACKUPS
        ]
      },
      "dashboards": {
        "<dashboard_id>": {
          "id": str, "owner_id": str, "name": str, "updated": iso8601,
          "shared_with": [ "<ha_user_id>", ... ],  # "*" means everyone
          "payload": <json>  # one serialised HKIDashboard
        }
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
            self._data.setdefault("dashboards", {})
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


    # ── Shared dashboards (Phase 2) ──────────────────────────────────────

    async def publish_dashboard(
        self,
        owner_id: str,
        name: str,
        payload: Any,
        shared_with: list[str],
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a shared dashboard. Returns its metadata (no payload)."""
        data = await self._load()
        dashboards: dict[str, Any] = data["dashboards"]
        did = dashboard_id or uuid.uuid4().hex
        entry = {
            "id": did,
            "owner_id": owner_id,
            "name": name,
            "updated": _now_iso(),
            "shared_with": list(dict.fromkeys(shared_with)),  # dedupe, keep order
            "payload": payload,
        }
        dashboards[did] = entry
        await self._save()
        return _dash_meta(entry)

    async def unpublish_dashboard(self, dashboard_id: str) -> bool:
        """Remove a shared dashboard. Returns True if it existed."""
        data = await self._load()
        removed = data["dashboards"].pop(dashboard_id, None) is not None
        if removed:
            await self._save()
        return removed

    async def list_dashboards_for(self, user_id: str, is_admin: bool) -> list[dict[str, Any]]:
        """Metadata (no payloads) of dashboards visible to ``user_id``.

        A user sees dashboards they own, dashboards shared explicitly with them,
        and dashboards shared with everyone. Admins additionally see everything so
        they can manage what has been published.
        """
        data = await self._load()
        out: list[dict[str, Any]] = []
        for entry in data["dashboards"].values():
            if (
                is_admin
                or entry["owner_id"] == user_id
                or user_id in entry["shared_with"]
                or "*" in entry["shared_with"]
            ):
                out.append(_dash_meta(entry))
        out.sort(key=lambda e: e.get("updated", ""), reverse=True)
        return out

    async def get_dashboard_for(
        self, user_id: str, is_admin: bool, dashboard_id: str
    ) -> Any | None:
        """Return the payload of a dashboard if ``user_id`` may see it, else None."""
        data = await self._load()
        entry = data["dashboards"].get(dashboard_id)
        if entry is None:
            return None
        if (
            is_admin
            or entry["owner_id"] == user_id
            or user_id in entry["shared_with"]
            or "*" in entry["shared_with"]
        ):
            return entry["payload"]
        return None


def _meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the payload from a backup entry for list/put responses."""
    return {k: v for k, v in entry.items() if k != "payload"}


def _dash_meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the payload from a dashboard entry for list/publish responses."""
    return {k: v for k, v in entry.items() if k != "payload"}
