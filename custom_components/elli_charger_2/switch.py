"""Local charging authorization controls for Elli Charger 2."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import ElliChargerEntity


def direct_authorization_state(data: dict) -> bool | None:
    """Decode the GET status; malformed/unknown replies are not false states."""
    response = data.get("charging_direct_authorization")
    if not isinstance(response, dict):
        return None
    value = response.get("value")
    if value in ("allowed", "allow"):
        return True
    if value in ("denied", "deny"):
        return False
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the authorization switch only when local login is configured."""
    coordinator = entry.runtime_data
    if coordinator.api.authentication_enabled:
        async_add_entities([ElliDirectAuthorizationSwitch(coordinator, entry.entry_id)])


class ElliDirectAuthorizationSwitch(ElliChargerEntity, SwitchEntity):
    """Allow or deny a charging authorization request on the local wallbox."""

    _attr_translation_key = "direct_authorization"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_direct_authorization"

    @property
    def is_on(self) -> bool | None:
        """Reflect the charger response; never assume a write was applied."""
        return direct_authorization_state(self.coordinator.data or {})

    async def async_turn_on(self, **kwargs) -> None:
        """Request charging authorization (not a transaction start)."""
        await self.coordinator.api.async_set_direct_authorization(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Deny charging authorization (not a transaction stop)."""
        await self.coordinator.api.async_set_direct_authorization(False)
        await self.coordinator.async_request_refresh()
