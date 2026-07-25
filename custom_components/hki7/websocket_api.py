"""WebSocket API for HKI 7 Cloud.

Every command is authenticated by Home Assistant before it reaches us, so
``connection.user`` is the trusted identity of the caller. That single fact is
what lets later phases share dashboards and apply per-user parental controls
without the app ever managing identity.

Phase 1 commands:
    hki7/whoami        -> {user_id, name, is_admin, is_owner}
    hki7/backup/put    -> stores the caller's UI backup blob, returns metadata
    hki7/backup/list   -> metadata of the caller's backups (newest first)
    hki7/backup/get    -> the payload of one of the caller's backups
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
