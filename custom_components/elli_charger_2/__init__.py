"""Elli Charger 2 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ElliChargerApi, ElliChargerAuthenticationError, ElliChargerConnectionError
from .const import CONF_USER_TYPE, PLATFORMS, USER_TYPE_STANDARD
from .coordinator import ElliChargerCoordinator

type ElliChargerConfigEntry = ConfigEntry[ElliChargerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ElliChargerConfigEntry) -> bool:
    """Set up Elli Charger 2 from a config entry."""
    api = ElliChargerApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.options.get(CONF_USER_TYPE, entry.data.get(CONF_USER_TYPE, USER_TYPE_STANDARD)),
        entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD, "")),
    )
    if api.authentication_enabled:
        try:
            await api.async_login()
        except ElliChargerAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ElliChargerConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err

    coordinator = ElliChargerCoordinator(hass, api)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    api.start_event_listener(coordinator.async_event_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ElliChargerConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.api.async_stop_event_listener()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
