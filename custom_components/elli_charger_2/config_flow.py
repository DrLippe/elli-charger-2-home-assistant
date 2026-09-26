"""Config flow for Elli Charger 2."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ElliChargerApi,
    ElliChargerAuthenticationError,
    ElliChargerConnectionError,
    normalize_host,
)
from .const import (
    CONF_USER_TYPE,
    DOMAIN,
    USER_TYPE_SERVICE,
    USER_TYPE_STANDARD,
)


class ElliChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elli Charger 2."""

    VERSION = 1

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
                    user_input[CONF_USER_TYPE],
                    user_input[CONF_PASSWORD],
                )
                await api.async_login()
                await api._request("GET", "/api/v2/charging/state", auth=False)
            except ValueError:
                errors["base"] = "invalid_host"
            except ElliChargerAuthenticationError:
                errors["base"] = "invalid_auth"
            except ElliChargerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(normalized.lower())
                self._abort_if_unique_id_configured()
                user_input[CONF_HOST] = normalized
                return self.async_create_entry(
                    title="Elli Charger 2",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required(CONF_USER_TYPE, default=USER_TYPE_STANDARD): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=USER_TYPE_STANDARD, label="Standard user"),
                            SelectOptionDict(value=USER_TYPE_SERVICE, label="Service user"),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="user_type",
                    )
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
