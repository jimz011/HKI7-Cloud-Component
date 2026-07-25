"""Config flow for HKI 7 Cloud.

A single-instance, no-input flow: the integration has nothing to configure in
Phase 1 (family roster and defaults are managed from the app in a later phase).
Adding it simply enables the hki7/* WebSocket API on this HA instance.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class Hki7ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HKI 7 Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="HKI 7 Cloud", data={})

        return self.async_show_form(step_id="user")
