"""Elli Charger 2 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ElliChargerApi
from .const import PLATFORMS
from .coordinator import ElliChargerCoordinator

type ElliChargerConfigEntry = ConfigEntry[ElliChargerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ElliChargerConfigEntry) -> bool:
    """Set up Elli Charger 2 from a config entry."""
    api = ElliChargerApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
    )

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
