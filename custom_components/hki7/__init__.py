"""The HKI 7 Cloud integration.

A local companion backend for the HKI 7 Home Assistant app. It stores app data
on the user's own HA instance and exposes it over the authenticated WebSocket
API, so identity (which HA user is calling) is handled by Home Assistant itself.

Phase 1: HA-local backups. Later phases add family dashboard sharing and
parental controls on top of the same store.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket_api
from .const import DOMAIN
from .store import Hki7Store


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HKI 7 Cloud from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if "store" not in domain_data:
        domain_data["store"] = Hki7Store(hass)
        websocket_api.async_register(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    The WebSocket commands are registered process-wide and cannot be
    unregistered, so we leave them in place; a reload simply reuses them.
    """
    return True
