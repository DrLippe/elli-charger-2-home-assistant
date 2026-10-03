"""Config flow for Elli Charger 2 with optional local authentication."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
    TextSelector, TextSelectorConfig, TextSelectorType,
)

from .api import (
    ElliChargerApi, ElliChargerAuthenticationError,
    ElliChargerConnectionError, normalize_host,
)
from .const import CONF_USER_TYPE, DOMAIN, USER_TYPE_SERVICE, USER_TYPE_STANDARD


def _credential_schema(user_type: str = USER_TYPE_STANDARD) -> dict:
    """Leave password empty to use only public endpoints."""
    return {
        vol.Optional(CONF_USER_TYPE, default=user_type): SelectSelector(
            SelectSelectorConfig(
                options=[USER_TYPE_STANDARD, USER_TYPE_SERVICE],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="user_type",
            )
        ),
        vol.Optional(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }


async def _validate(hass, host: str, credentials: dict[str, Any]) -> None:
    """Check public connectivity and, if supplied, the credentials."""
    api = ElliChargerApi(
        async_get_clientsession(hass), host,
        credentials.get(CONF_USER_TYPE, USER_TYPE_STANDARD),
        credentials.get(CONF_PASSWORD, ""),
    )
    await api._request("GET", "/api/v2/charging/state", auth=False)
    if api.authentication_enabled:
        await api.async_login()


class ElliChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elli Charger 2."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Allow existing entries to enable or disable authentication."""
        return ElliChargerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalized = normalize_host(user_input[CONF_HOST])
                await _validate(self.hass, normalized, user_input)
            except ValueError:
                errors["base"] = "invalid_host"
            except ElliChargerAuthenticationError:
                errors["base"] = "invalid_auth"
            except ElliChargerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(normalized.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Elli Charger 2",
                    data={**user_input, CONF_HOST: normalized},
                )

        schema = vol.Schema({
            vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            **_credential_schema((user_input or {}).get(CONF_USER_TYPE, USER_TYPE_STANDARD)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Repair credentials or switch back to unauthenticated access."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {
                CONF_USER_TYPE: user_input.get(CONF_USER_TYPE, USER_TYPE_STANDARD),
                CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
            }
            try:
                await _validate(self.hass, entry.data[CONF_HOST], credentials)
            except ElliChargerAuthenticationError:
                errors["base"] = "invalid_auth"
            except ElliChargerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, options={**entry.options, **credentials}
                )
        user_type = entry.options.get(
            CONF_USER_TYPE, entry.data.get(CONF_USER_TYPE, USER_TYPE_STANDARD)
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(_credential_schema(user_type)), errors=errors,
        )


class ElliChargerOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage optional credentials on existing installations."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {
                CONF_USER_TYPE: user_input.get(CONF_USER_TYPE, USER_TYPE_STANDARD),
                CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
            }
            try:
                await _validate(self.hass, self.config_entry.data[CONF_HOST], credentials)
            except ElliChargerAuthenticationError:
                errors["base"] = "invalid_auth"
            except ElliChargerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="", data=credentials)

        user_type = self.config_entry.options.get(
            CONF_USER_TYPE, self.config_entry.data.get(CONF_USER_TYPE, USER_TYPE_STANDARD)
        )
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_credential_schema(user_type)), errors=errors
        )
