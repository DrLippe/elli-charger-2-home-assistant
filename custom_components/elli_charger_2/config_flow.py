"""Config flow for Elli Charger 2."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import ElliChargerApi, ElliChargerConnectionError, normalize_host
from .const import DOMAIN


class ElliChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elli Charger 2."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set up the integration from the UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = normalize_host(user_input[CONF_HOST])
                api = ElliChargerApi(
                    async_get_clientsession(self.hass),
                    normalized,
                )
                await api._request("GET", "/api/v2/charging/state")
            except ValueError:
                errors["base"] = "invalid_host"
            except ElliChargerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(normalized.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Elli Charger 2",
                    data={CONF_HOST: normalized},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
