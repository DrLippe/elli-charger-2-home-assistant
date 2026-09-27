"""Binary sensors for Elli Charger 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import ElliChargerEntity


@dataclass(frozen=True, kw_only=True)
class ElliBinarySensorDescription(BinarySensorEntityDescription):
    """Describe an Elli Charger binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[ElliBinarySensorDescription, ...] = (
    ElliBinarySensorDescription(
        key="vehicle_connected",
        translation_key="vehicle_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-type2",
        value_fn=lambda d: d.get("plugged_vehicle") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elli Charger binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ElliBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class ElliBinarySensor(ElliChargerEntity, BinarySensorEntity):
    """Representation of an Elli Charger binary sensor."""

    entity_description: ElliBinarySensorDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: ElliBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return binary state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return vehicle details when available."""
        vehicle = self.coordinator.data.get("plugged_vehicle")
        if isinstance(vehicle, dict):
            return vehicle

        session = self.coordinator.data.get("last_session")
        if not isinstance(session, dict):
            return None

        return {
            "brand": session.get("brand"),
            "model": session.get("model"),
            "name": session.get("name"),
            "latest_soc": session.get("latestSOC"),
            "target_soc": session.get("targetSOC"),
            "range": session.get("range"),
        }
