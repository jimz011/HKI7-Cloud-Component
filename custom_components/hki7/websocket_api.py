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
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, MAX_PAYLOAD_BYTES
from .store import Hki7Store


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


def _store(hass: HomeAssistant) -> Hki7Store:
    return hass.data[DOMAIN]["store"]


@callback
@websocket_api.websocket_command({vol.Required("type"): "hki7/whoami"})
def ws_whoami(hass, connection, msg) -> None:
    """Return the calling user's identity so the app can key its features on it."""
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
    connection.send_result(msg["id"], meta)


@websocket_api.websocket_command(
    {vol.Required("type"): "hki7/dashboard/unpublish", vol.Required("dashboard_id"): str}
)
@websocket_api.async_response
async def ws_dashboard_unpublish(hass, connection, msg) -> None:
    """Remove a shared dashboard (admin only)."""
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin only")
        return
    removed = await _store(hass).unpublish_dashboard(msg["dashboard_id"])
    connection.send_result(msg["id"], {"removed": removed})


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
