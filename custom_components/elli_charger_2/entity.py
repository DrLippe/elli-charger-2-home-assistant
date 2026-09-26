"""Entity helpers for Elli Charger 2."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ElliChargerCoordinator


class ElliChargerEntity(CoordinatorEntity[ElliChargerCoordinator]):
    """Base entity for Elli Charger 2."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ElliChargerCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Elli Charger 2",
            manufacturer="Elli",
            model="Charger 2 Connect",
            configuration_url=coordinator.api.base_url,
        )
