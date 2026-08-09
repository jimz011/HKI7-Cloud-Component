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
      },
      "policies": {
        "<ha_user_id>": {
          "hidden_views": [str], "hidden_rooms": [str],
          "allow_edit": bool, "aesthetics_only": bool,
          "show_global_search": bool, "show_flows": bool,
          "allow_dashboard_switch": bool, "allow_dashboard_create": bool,
          "allow_reimport": bool,
          "visible_search_domains": [str], "visible_search_entity_ids": [str],
          "hidden_search_domains": [str], "hidden_search_entity_ids": [str]
        }
      },
      "devices": {
        "<ha_user_id>": {
          "<install_id>": {
            "device_id": str, "device_name": str, "app_version": str,
            "app_version_code": int, "os_version": str, "model": str,
            "user_name": str, "reported": iso8601,
            # Admin's "update this one phone" request, cleared once it reports a
            # version that satisfies it.
            "nudge_version_code": int | None, "nudge_version_name": str | None
          }
        }
      },
      "app_update": {
        # The household's minimum app version. Every device below it is prompted to update.
        "min_version_code": int | None, "min_version_name": str,
        "set_by": "<ha_user_id>", "set_at": iso8601
      },
      "events": {
        # The household's event-timeline roster: which entities the app shows a
        # "what happened" feed for. Set once by an admin rather than per device, so a
        # large family is not configured phone by phone. Who may see which of these is a
        # per-user concern and lives in "policies" (hidden_event_*), not here.
        "entity_ids": [str],
        "set_by": "<ha_user_id>", "set_at": iso8601
      }
    }
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEVICE_REPORT_MIN_INTERVAL_SECONDS,
    MAX_BACKUPS,
    MAX_DEVICES_PER_USER,
    MAX_EVENT_ENTITIES,
    STORAGE_KEY,
    STORAGE_VERSION,
)


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
            self._data.setdefault("policies", {})
            self._data.setdefault("devices", {})
            self._data.setdefault("app_update", {})
            self._data.setdefault("events", {})
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
    ) -> dict[str, Any] | None:
        """Create/update an owned dashboard, rejecting another owner's id."""
        data = await self._load()
        dashboards: dict[str, Any] = data["dashboards"]
        did = dashboard_id or uuid.uuid4().hex
        existing = dashboards.get(did)
        if existing is not None and existing.get("owner_id") != owner_id:
            return None
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

    async def unpublish_dashboard(self, owner_id: str, dashboard_id: str) -> bool | None:
        """Remove an owned dashboard; return None for an ownership violation."""
        data = await self._load()
        dashboards: dict[str, Any] = data["dashboards"]
        existing = dashboards.get(dashboard_id)
        if existing is not None and existing.get("owner_id") != owner_id:
            return None
        removed = dashboards.pop(dashboard_id, None) is not None
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


    # ── Parental-control policies & per-user permissions (Phase 3) ───────

    async def set_policy(
        self,
        user_id: str,
        hidden_views: list[str],
        hidden_rooms: list[str],
        allow_edit: bool = True,
        aesthetics_only: bool = False,
        show_global_search: bool = True,
        show_flows: bool = True,
        allow_dashboard_switch: bool = True,
        allow_dashboard_create: bool = True,
        allow_reimport: bool = True,
        hidden_item_ids: list[str] | None = None,
        visible_search_domains: list[str] | None = None,
        visible_search_entity_ids: list[str] | None = None,
        hidden_search_domains: list[str] | None = None,
        hidden_search_entity_ids: list[str] | None = None,
        room_follow: dict[str, Any] | None = None,
        hidden_event_entity_ids: list[str] | None = None,
        hidden_event_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Set (or clear) one user's policy — hidden views/rooms plus edit and visibility
        permissions. Returns the stored, fully-populated policy."""
        data = await self._load()
        policies: dict[str, Any] = data["policies"]
        previous = _full_policy(policies.get(user_id))
        policy = {
            "hidden_views": list(dict.fromkeys(hidden_views)),
            "hidden_rooms": list(dict.fromkeys(hidden_rooms)),
            "allow_edit": allow_edit,
            "aesthetics_only": aesthetics_only,
            "show_global_search": show_global_search,
            "show_flows": show_flows,
            "allow_dashboard_switch": allow_dashboard_switch,
            "allow_dashboard_create": allow_dashboard_create,
            "allow_reimport": allow_reimport,
            "hidden_item_ids": previous["hidden_item_ids"] if hidden_item_ids is None else list(dict.fromkeys(hidden_item_ids)),
            "visible_search_domains": previous["visible_search_domains"] if visible_search_domains is None else list(dict.fromkeys(visible_search_domains)),
            "visible_search_entity_ids": previous["visible_search_entity_ids"] if visible_search_entity_ids is None else list(dict.fromkeys(visible_search_entity_ids)),
            "hidden_search_domains": previous["hidden_search_domains"] if hidden_search_domains is None else list(dict.fromkeys(hidden_search_domains)),
            "hidden_search_entity_ids": previous["hidden_search_entity_ids"] if hidden_search_entity_ids is None else list(dict.fromkeys(hidden_search_entity_ids)),
            "room_follow": previous["room_follow"] if room_follow is None else _full_room_follow(room_follow),
            "hidden_event_entity_ids": previous["hidden_event_entity_ids"] if hidden_event_entity_ids is None else list(dict.fromkeys(hidden_event_entity_ids)),
            "hidden_event_domains": previous["hidden_event_domains"] if hidden_event_domains is None else list(dict.fromkeys(hidden_event_domains)),
        }
        # Store nothing for an all-default policy so an untouched user leaves no footprint.
        if policy == _default_policy():
            policies.pop(user_id, None)
        else:
            policies[user_id] = policy
        await self._save()
        return policy

    async def get_policy(self, user_id: str) -> dict[str, Any]:
        """Return one user's policy (defaults if none set), backfilling any missing fields."""
        data = await self._load()
        return _full_policy(data["policies"].get(user_id))

    async def list_policies(self) -> dict[str, Any]:
        """Return every stored policy, keyed by user id (admin view), with defaults backfilled."""
        data = await self._load()
        return {uid: _full_policy(p) for uid, p in data["policies"].items()}

    async def room_follow_roster(self) -> list[str]:
        """The room-presence sensors tracked across the household, for the people-per-room
        counter. Readable by any user because counting needs the sensor ids and nothing else —
        no user ids, no other policy field, and every id is an entity the caller can already
        read straight from Home Assistant."""
        data = await self._load()
        sensors: list[str] = []
        for stored in data["policies"].values():
            follow = _full_room_follow(stored.get("room_follow"))
            sensor = follow["sensor_entity_id"]
            if follow["enabled"] and sensor and sensor not in sensors:
                sensors.append(sensor)
        return sensors

    async def get_events_roster(self) -> list[str]:
        """The household's full event-timeline roster, exactly as the admin set it."""
        data = await self._load()
        stored = data.get("events") or {}
        return list(stored.get("entity_ids") or [])

    async def set_events_roster(self, set_by: str, entity_ids: list[str]) -> list[str]:
        """Replace the household's event roster and return what was stored.

        Capped at MAX_EVENT_ENTITIES: the app opens one logbook subscription covering every id
        here, so an unbounded roster is a performance problem on each family phone rather than
        merely a large storage record.
        """
        data = await self._load()
        cleaned = [e for e in dict.fromkeys(entity_ids) if isinstance(e, str) and "." in e]
        del cleaned[MAX_EVENT_ENTITIES:]
        if cleaned:
            data["events"] = {
                "entity_ids": cleaned,
                "set_by": set_by,
                "set_at": _now_iso(),
            }
        else:
            # An empty roster is the feature being switched off, so leave no record behind.
            data["events"] = {}
        await self._save()
        return cleaned

    async def events_roster_for(self, user_id: str) -> list[str]:
        """The roster with this person's hidden entities and domains removed.

        Filtering here rather than in the app means a restricted account is never told which
        entities it is being kept away from — it simply receives a shorter list. This is still a
        Home Assistant account that can read those entities directly, so this hides the timeline,
        not the underlying state; it is the same guarantee hidden rooms and views already give.
        """
        roster = await self.get_events_roster()
        policy = await self.get_policy(user_id)
        hidden_ids = set(policy["hidden_event_entity_ids"])
        hidden_domains = set(policy["hidden_event_domains"])
        return [
            entity_id
            for entity_id in roster
            if entity_id not in hidden_ids
            and entity_id.split(".", 1)[0] not in hidden_domains
        ]


    # ── App installs (Phase 4) ───────────────────────────────────────────

    async def report_device(
        self,
        user_id: str,
        user_name: str,
        device_id: str,
        device_name: str,
        app_version: str,
        app_version_code: int | None = None,
        os_version: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Record one app install for ``user_id`` and return the stored record.

        ``user_id`` comes from the authenticated connection, never from the client, so a device
        can only ever report itself as the account it is signed in as.
        """
        data = await self._load()
        devices: dict[str, Any] = data["devices"].setdefault(user_id, {})
        previous = devices.get(device_id)
        entry = {
            "device_id": device_id,
            "device_name": device_name,
            "app_version": app_version,
            "app_version_code": app_version_code,
            "os_version": os_version,
            "model": model,
            "user_name": user_name,
            "reported": _now_iso(),
        }
        # A pending "update this phone" request belongs to the device, not to the report, so it
        # survives every report — until the version it asked for actually arrives, which is the
        # request being satisfied rather than ignored.
        nudge_code = (previous or {}).get("nudge_version_code")
        if nudge_code is not None and app_version_code is not None and app_version_code >= nudge_code:
            nudge_code = None
        if nudge_code is not None:
            entry["nudge_version_code"] = nudge_code
            entry["nudge_version_name"] = (previous or {}).get("nudge_version_name")
        # The app reports on every foreground. Persist only a real change, or a "last seen" that
        # has gone stale enough to be worth a disk write.
        if (
            previous is not None
            and _device_facts(previous) == _device_facts(entry)
            and _seconds_since(previous.get("reported")) < DEVICE_REPORT_MIN_INTERVAL_SECONDS
        ):
            return previous
        devices[device_id] = entry
        if len(devices) > MAX_DEVICES_PER_USER:
            newest = sorted(
                devices.items(), key=lambda kv: kv[1].get("reported") or "", reverse=True
            )[:MAX_DEVICES_PER_USER]
            data["devices"][user_id] = dict(newest)
        await self._save()
        return entry

    async def list_devices(self) -> list[dict[str, Any]]:
        """Every reported app install across the household, for the admin's device list."""
        data = await self._load()
        out: list[dict[str, Any]] = []
        for user_id, devices in data["devices"].items():
            for entry in devices.values():
                out.append({**entry, "user_id": user_id})
        out.sort(key=lambda e: ((e.get("user_name") or "").lower(), (e.get("device_name") or "").lower()))
        return out

    async def max_reported_version_code(self) -> int | None:
        """The highest app version any device has reported, or None if nobody has yet."""
        data = await self._load()
        codes = [
            entry.get("app_version_code")
            for devices in data["devices"].values()
            for entry in devices.values()
            if isinstance(entry.get("app_version_code"), int)
        ]
        return max(codes) if codes else None

    async def get_app_update_policy(self) -> dict[str, Any]:
        """The household's minimum app version, or an empty requirement when none is set."""
        data = await self._load()
        stored = data.get("app_update") or {}
        return {
            "min_version_code": stored.get("min_version_code"),
            "min_version_name": stored.get("min_version_name") or "",
            "set_by": stored.get("set_by") or "",
            "set_at": stored.get("set_at") or "",
        }

    async def set_app_update_policy(
        self, set_by: str, min_version_code: int | None, min_version_name: str | None
    ) -> dict[str, Any] | None:
        """Set or clear the household's minimum app version.

        Returns None when asked for a version no device has ever reported. Nothing here can install
        an app, so a requirement above what actually exists could only ever leave the family staring
        at a prompt they cannot satisfy; refusing it is the one guard the component can offer.
        """
        data = await self._load()
        if min_version_code is None:
            data["app_update"] = {}
            await self._save()
            return await self.get_app_update_policy()
        highest = await self.max_reported_version_code()
        if highest is None or min_version_code > highest:
            return None
        data["app_update"] = {
            "min_version_code": min_version_code,
            "min_version_name": min_version_name or "",
            "set_by": set_by,
            "set_at": _now_iso(),
        }
        await self._save()
        return await self.get_app_update_policy()

    async def nudge_device(
        self, user_id: str, device_id: str, version_code: int | None, version_name: str | None
    ) -> bool:
        """Ask one device to update to [version_code], or clear its pending request with None.

        Refused for a version no device has reported, for the same reason as the household
        minimum. True when the device exists and the request was stored.
        """
        data = await self._load()
        entry = data["devices"].get(user_id, {}).get(device_id)
        if entry is None:
            return False
        if version_code is None:
            entry.pop("nudge_version_code", None)
            entry.pop("nudge_version_name", None)
            await self._save()
            return True
        highest = await self.max_reported_version_code()
        if highest is None or version_code > highest:
            return False
        entry["nudge_version_code"] = version_code
        entry["nudge_version_name"] = version_name or ""
        await self._save()
        return True

    async def forget_device(self, user_id: str, device_id: str) -> bool:
        """Drop one remembered install (an uninstalled or replaced phone). True if it existed."""
        data = await self._load()
        devices: dict[str, Any] = data["devices"].get(user_id, {})
        if devices.pop(device_id, None) is None:
            return False
        if not devices:
            data["devices"].pop(user_id, None)
        await self._save()
        return True


def _device_facts(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Everything about a device except when it was last seen.

    Includes the pending nudge so that clearing a satisfied one is never mistaken for "nothing
    changed" and left in storage to nag a device that has already updated.
    """
    return tuple(
        entry.get(key)
        for key in (
            "device_name",
            "app_version",
            "app_version_code",
            "os_version",
            "model",
            "user_name",
            "nudge_version_code",
        )
    )


def _seconds_since(iso: str | None) -> float:
    """Age of an ISO-8601 timestamp in seconds; treated as ancient when missing or unparsable."""
    if not iso:
        return float("inf")
    try:
        stored = datetime.fromisoformat(iso)
    except ValueError:
        return float("inf")
    # A record written by some other tool could be naive; treat it as UTC rather than raising.
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stored).total_seconds()


def _full_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Return a policy with every field present, filling defaults for older stored records that
    predate the edit/visibility permissions (or for a user with no policy at all)."""
    policy = policy or {}
    return {
        "hidden_views": policy.get("hidden_views", []),
        "hidden_rooms": policy.get("hidden_rooms", []),
        "allow_edit": policy.get("allow_edit", True),
        "aesthetics_only": policy.get("aesthetics_only", False),
        "show_global_search": policy.get("show_global_search", True),
        "show_flows": policy.get("show_flows", True),
        "allow_dashboard_switch": policy.get("allow_dashboard_switch", True),
        "allow_dashboard_create": policy.get("allow_dashboard_create", True),
        "allow_reimport": policy.get("allow_reimport", True),
        "hidden_item_ids": policy.get("hidden_item_ids", []),
        "visible_search_domains": policy.get("visible_search_domains", []),
        "visible_search_entity_ids": policy.get("visible_search_entity_ids", []),
        "hidden_search_domains": policy.get("hidden_search_domains", []),
        "hidden_search_entity_ids": policy.get("hidden_search_entity_ids", []),
        "room_follow": _full_room_follow(policy.get("room_follow")),
        # Entities and whole domains from the household event roster that this person must not
        # see a timeline for. Subtractive rather than an allow-list: an admin curates the roster
        # once for everybody, then takes entries away from the people who shouldn't have them.
        "hidden_event_entity_ids": policy.get("hidden_event_entity_ids", []),
        "hidden_event_domains": policy.get("hidden_event_domains", []),
    }


def _full_room_follow(follow: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise one user's room-following settings.

    ``sensor_entity_id`` is that person's room-presence sensor (ESPresense and mqtt_room both
    publish the room name as the state). ``state_rooms`` only holds overrides — the app matches
    a state against the area names itself, so a household whose rooms are named after its areas
    needs no mapping at all.
    """
    follow = follow or {}
    sensor = follow.get("sensor_entity_id") or None
    state_rooms = follow.get("state_rooms") or {}
    return {
        "sensor_entity_id": sensor,
        # Following is meaningless without a sensor, so it can never be on without one.
        "enabled": bool(follow.get("enabled", False)) and sensor is not None,
        "open_on_launch": bool(follow.get("open_on_launch", True)),
        # False stops tracking after that initial placement — no prompts, no silent moves — so
        # open_on_launch is the only thing this person's following does once the app is open.
        "continue_after_launch": bool(follow.get("continue_after_launch", True)),
        "prompt_on_move": bool(follow.get("prompt_on_move", True)),
        # Seconds the new room must hold before it counts as a real move. Room-presence sensors
        # flap between adjacent rooms, so 0 would mean a prompt every few seconds.
        "dwell_seconds": max(0, min(600, int(follow.get("dwell_seconds", 20)))),
        "state_rooms": {str(k): str(v) for k, v in state_rooms.items()},
    }


def _default_policy() -> dict[str, Any]:
    """The unrestricted policy: nothing hidden, everything allowed."""
    return _full_policy(None)


def _meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the payload from a backup entry for list/put responses."""
    return {k: v for k, v in entry.items() if k != "payload"}


def _dash_meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the payload from a dashboard entry for list/publish responses."""
    return {k: v for k, v in entry.items() if k != "payload"}
