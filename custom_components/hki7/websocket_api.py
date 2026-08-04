"""WebSocket API for HKI 7 Cloud.

Every command is authenticated by Home Assistant before it reaches us, so
``connection.user`` is the trusted identity of the caller. That single fact is
what lets later phases share dashboards and apply per-user parental controls
without the app ever managing identity.

Commands:
    hki7/whoami              -> {user_id, name, is_admin, is_owner}
    hki7/backup/put          -> stores the caller's UI backup blob, returns metadata
    hki7/backup/list         -> metadata of the caller's backups (newest first)
    hki7/backup/get          -> the payload of one of the caller's backups
    hki7/users/list          -> (admin) HA users, for the "share with" picker
    hki7/dashboard/publish   -> (admin) create/update a shared dashboard
    hki7/dashboard/unpublish -> (admin) remove a shared dashboard
    hki7/dashboard/list      -> dashboards visible to the caller (metadata only)
    hki7/dashboard/get       -> the payload of a dashboard the caller may see
    hki7/policy/set          -> (admin) set a user's hidden views/rooms + edit/visibility permissions
    hki7/policy/get          -> the CALLING user's own policy (never anyone else's)
    hki7/policy/list         -> (admin) every stored policy, for the editor
    hki7/room_follow/roster  -> the household's room-presence sensor ids (any user)
    hki7/adaptive_lighting/list -> each Adaptive Lighting profile's light membership (any user)
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, MAX_PAYLOAD_BYTES
from .store import Hki7Store

EVENT_DASHBOARD_UPDATED = "hki7_dashboard_updated"

# One person's room-following settings. Every field is optional so the app can send a partial
# update; store._full_room_follow fills the rest and clamps dwell_seconds.
_ROOM_FOLLOW_SCHEMA = vol.Schema(
    {
        vol.Optional("sensor_entity_id"): vol.Any(str, None),
        vol.Optional("enabled"): bool,
        vol.Optional("open_on_launch"): bool,
        vol.Optional("continue_after_launch"): bool,
        vol.Optional("prompt_on_move"): bool,
        vol.Optional("dwell_seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
        # Sensor state -> area id, holding only the states the app could not match to an area.
        vol.Optional("state_rooms"): {str: str},
    }
)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all hki7/* WebSocket commands."""
    websocket_api.async_register_command(hass, ws_whoami)
    websocket_api.async_register_command(hass, ws_backup_put)
    websocket_api.async_register_command(hass, ws_backup_list)
    websocket_api.async_register_command(hass, ws_backup_get)
    websocket_api.async_register_command(hass, ws_users_list)
    websocket_api.async_register_command(hass, ws_dashboard_publish)
    websocket_api.async_register_command(hass, ws_dashboard_unpublish)
    websocket_api.async_register_command(hass, ws_dashboard_list)
    websocket_api.async_register_command(hass, ws_dashboard_get)
    websocket_api.async_register_command(hass, ws_policy_set)
    websocket_api.async_register_command(hass, ws_policy_get)
    websocket_api.async_register_command(hass, ws_policy_list)
    websocket_api.async_register_command(hass, ws_room_follow_roster)
    websocket_api.async_register_command(hass, ws_adaptive_lighting_list)


def _is_active(hass: HomeAssistant) -> bool:
    """True only while the integration's config entry is loaded (see __init__)."""
    return bool(hass.data.get(DOMAIN, {}).get("active"))


def _store(hass: HomeAssistant) -> Hki7Store:
    # Raises when the integration has been removed, so every data command fails and the app treats
    # the component as unavailable rather than silently succeeding against orphaned storage.
    if not _is_active(hass):
        raise HomeAssistantError("HKI 7 Cloud is not set up")
    return hass.data[DOMAIN]["store"]


@callback
@websocket_api.websocket_command({vol.Required("type"): "hki7/whoami"})
def ws_whoami(hass, connection, msg) -> None:
    """Return the calling user's identity so the app can key its features on it."""
    if not _is_active(hass):
        connection.send_error(msg["id"], "unavailable", "HKI 7 Cloud is not set up")
        return
    user = connection.user
    connection.send_result(
        msg["id"],
        {
            "user_id": user.id,
            "name": user.name,
            "is_admin": user.is_admin,
            "is_owner": user.is_owner,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hki7/backup/put",
        vol.Required("payload"): dict,
        vol.Optional("label"): str,
    }
)
@websocket_api.async_response
async def ws_backup_put(hass, connection, msg) -> None:
    """Store the caller's UI backup blob on this HA instance."""
    payload: dict[str, Any] = msg["payload"]
    if len(str(payload)) > MAX_PAYLOAD_BYTES:
        connection.send_error(msg["id"], "payload_too_large", "Backup payload exceeds the size limit")
        return
    meta = await _store(hass).put_backup(connection.user.id, payload, msg.get("label"))
    connection.send_result(msg["id"], meta)


@websocket_api.websocket_command({vol.Required("type"): "hki7/backup/list"})
@websocket_api.async_response
async def ws_backup_list(hass, connection, msg) -> None:
    """List metadata for the caller's own backups (never anyone else's)."""
    backups = await _store(hass).list_backups(connection.user.id)
    connection.send_result(msg["id"], {"backups": backups})


@websocket_api.websocket_command(
    {vol.Required("type"): "hki7/backup/get", vol.Required("backup_id"): str}
)
@websocket_api.async_response
async def ws_backup_get(hass, connection, msg) -> None:
    """Return one of the caller's backup payloads, or an error if not found."""
    payload = await _store(hass).get_backup(connection.user.id, msg["backup_id"])
    if payload is None:
        connection.send_error(msg["id"], "not_found", "Backup not found")
        return
    connection.send_result(msg["id"], {"payload": payload})


@websocket_api.websocket_command({vol.Required("type"): "hki7/users/list"})
@websocket_api.async_response
async def ws_users_list(hass, connection, msg) -> None:
    """List Home Assistant users so the admin can choose who to share with."""
    if not _is_active(hass):
        connection.send_error(msg["id"], "unavailable", "HKI 7 Cloud is not set up")
        return
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    users = []
    for user in await hass.auth.async_get_users():
        # Skip disabled accounts and non-human system users (e.g. the Supervisor).
        if not user.is_active or user.system_generated:
            continue
        users.append({"id": user.id, "name": user.name, "is_admin": user.is_admin})
    connection.send_result(msg["id"], {"users": users})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hki7/dashboard/publish",
        vol.Required("name"): str,
        vol.Required("payload"): dict,
        vol.Required("shared_with"): [str],
        vol.Optional("dashboard_id"): str,
    }
)
@websocket_api.async_response
async def ws_dashboard_publish(hass, connection, msg) -> None:
    """Create or update a shared dashboard (admin only)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    if len(str(msg["payload"])) > MAX_PAYLOAD_BYTES:
        connection.send_error(msg["id"], "payload_too_large", "Dashboard payload exceeds the size limit")
        return
    meta = await _store(hass).publish_dashboard(
        owner_id=connection.user.id,
        name=msg["name"],
        payload=msg["payload"],
        shared_with=msg["shared_with"],
        dashboard_id=msg.get("dashboard_id"),
    )
    if meta is None:
        connection.send_error(msg["id"], "unauthorized", "Only the dashboard owner may update it")
        return
    connection.send_result(msg["id"], meta)
    hass.bus.async_fire(
        EVENT_DASHBOARD_UPDATED,
        {"dashboard_id": meta["id"], "owner_id": connection.user.id, "action": "published"},
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "hki7/dashboard/unpublish", vol.Required("dashboard_id"): str}
)
@websocket_api.async_response
async def ws_dashboard_unpublish(hass, connection, msg) -> None:
    """Remove a shared dashboard (admin only)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    removed = await _store(hass).unpublish_dashboard(connection.user.id, msg["dashboard_id"])
    if removed is None:
        connection.send_error(msg["id"], "unauthorized", "Only the dashboard owner may unpublish it")
        return
    connection.send_result(msg["id"], {"removed": removed})
    if removed:
        hass.bus.async_fire(
            EVENT_DASHBOARD_UPDATED,
            {"dashboard_id": msg["dashboard_id"], "owner_id": connection.user.id, "action": "unpublished"},
        )


@websocket_api.websocket_command({vol.Required("type"): "hki7/dashboard/list"})
@websocket_api.async_response
async def ws_dashboard_list(hass, connection, msg) -> None:
    """List dashboards visible to the caller (metadata only, ACL-filtered)."""
    user = connection.user
    dashboards = await _store(hass).list_dashboards_for(user.id, user.is_admin)
    connection.send_result(msg["id"], {"dashboards": dashboards})


@websocket_api.websocket_command(
    {vol.Required("type"): "hki7/dashboard/get", vol.Required("dashboard_id"): str}
)
@websocket_api.async_response
async def ws_dashboard_get(hass, connection, msg) -> None:
    """Return a dashboard payload if the caller may see it, else an error."""
    user = connection.user
    payload = await _store(hass).get_dashboard_for(user.id, user.is_admin, msg["dashboard_id"])
    if payload is None:
        connection.send_error(msg["id"], "not_found", "Dashboard not found or not shared with you")
        return
    connection.send_result(msg["id"], {"payload": payload})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hki7/policy/set",
        vol.Required("user_id"): str,
        vol.Required("hidden_views"): [str],
        vol.Required("hidden_rooms"): [str],
        # Per-user permissions. Optional so an older app that sends only the hidden lists keeps
        # working; each falls back to its unrestricted default.
        vol.Optional("allow_edit", default=True): bool,
        vol.Optional("aesthetics_only", default=False): bool,
        vol.Optional("show_global_search", default=True): bool,
        vol.Optional("show_flows", default=True): bool,
        vol.Optional("allow_dashboard_switch", default=True): bool,
        vol.Optional("allow_dashboard_create", default=True): bool,
        vol.Optional("allow_reimport", default=True): bool,
        vol.Optional("hidden_item_ids"): [str],
        vol.Optional("visible_search_domains"): [str],
        vol.Optional("visible_search_entity_ids"): [str],
        vol.Optional("hidden_search_domains"): [str],
        vol.Optional("hidden_search_entity_ids"): [str],
        vol.Optional("room_follow"): _ROOM_FOLLOW_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_policy_set(hass, connection, msg) -> None:
    """Set a user's hidden views/rooms and edit/visibility permissions (admin only)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    policy = await _store(hass).set_policy(
        msg["user_id"],
        msg["hidden_views"],
        msg["hidden_rooms"],
        allow_edit=msg["allow_edit"],
        aesthetics_only=msg["aesthetics_only"],
        show_global_search=msg["show_global_search"],
        show_flows=msg["show_flows"],
        allow_dashboard_switch=msg["allow_dashboard_switch"],
        allow_dashboard_create=msg["allow_dashboard_create"],
        allow_reimport=msg["allow_reimport"],
        hidden_item_ids=msg.get("hidden_item_ids"),
        visible_search_domains=msg.get("visible_search_domains"),
        visible_search_entity_ids=msg.get("visible_search_entity_ids"),
        hidden_search_domains=msg.get("hidden_search_domains"),
        hidden_search_entity_ids=msg.get("hidden_search_entity_ids"),
        room_follow=msg.get("room_follow"),
    )
    connection.send_result(msg["id"], policy)


@websocket_api.websocket_command({vol.Required("type"): "hki7/room_follow/roster"})
@websocket_api.async_response
async def ws_room_follow_roster(hass, connection, msg) -> None:
    """Return the household's room-presence sensor ids, for the people-per-room counter.

    Deliberately open to any authenticated user: counting people in a room needs the sensor ids
    and nothing else, and every id here is an entity the caller can already read directly from
    Home Assistant. No user ids and no other policy field are exposed.
    """
    sensors = await _store(hass).room_follow_roster()
    connection.send_result(msg["id"], {"sensors": sensors})


@websocket_api.websocket_command({vol.Required("type"): "hki7/policy/get"})
@websocket_api.async_response
async def ws_policy_get(hass, connection, msg) -> None:
    """Return the CALLING user's own policy — never anyone else's."""
    policy = await _store(hass).get_policy(connection.user.id)
    connection.send_result(msg["id"], policy)


@websocket_api.websocket_command({vol.Required("type"): "hki7/policy/list"})
@websocket_api.async_response
async def ws_policy_list(hass, connection, msg) -> None:
    """Return every stored policy for the admin editor (admin only)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    policies = await _store(hass).list_policies()
    connection.send_result(msg["id"], {"policies": policies})


@callback
@websocket_api.websocket_command({vol.Required("type"): "hki7/adaptive_lighting/list"})
def ws_adaptive_lighting_list(hass, connection, msg) -> None:
    """Return each Adaptive Lighting profile's light membership, keyed by config-entry id.

    The app normally reads this from the integration's options flow, which Home Assistant restricts
    to admins. Serving it here (to any authenticated user) lets non-admin family members get the same
    per-room Adaptive Lighting controls the admin sees. It only exposes which lights each profile
    already controls — no configuration is changed.
    """
    if not _is_active(hass):
        connection.send_error(msg["id"], "unavailable", "HKI 7 Cloud is not set up")
        return
    profiles: dict[str, list[str]] = {}
    for entry in hass.config_entries.async_entries("adaptive_lighting"):
        lights = entry.options.get("lights")
        if lights is None:
            lights = entry.data.get("lights", [])
        if isinstance(lights, str):
            lights = [lights]
        profiles[entry.entry_id] = [str(light) for light in (lights or [])]
    connection.send_result(msg["id"], {"profiles": profiles})
