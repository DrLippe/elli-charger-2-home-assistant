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

    requires_auth: bool = False
    value_fn: Callable[[dict[str, Any]], bool | None]


def _bool_field(data: dict[str, Any], group: str, key: str) -> bool | None:
    value = data.get(group)
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    result = value.get(key)
    return result if isinstance(result, bool) else None


BINARY_SENSORS: tuple[ElliBinarySensorDescription, ...] = (
    ElliBinarySensorDescription(
        key="vehicle_connected",
        translation_key="vehicle_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-type2",
        value_fn=lambda d: d.get("plugged_vehicle") is not None,
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="ethernet_connected",
        translation_key="ethernet_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: _bool_field(d, "ethernet_connected", "connected"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="network_connected",
        translation_key="network_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: _bool_field(d, "network_connected", "connected"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="wlan_connected",
        translation_key="wlan_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: _bool_field(d, "wlan_connected", "connected"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="lte_connected",
        translation_key="lte_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: _bool_field(d, "lte_connected", "connected"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="ocpp_enabled",
        translation_key="ocpp_enabled",
        value_fn=lambda d: _bool_field(d, "ocpp_enabled", "enabled"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="ocpp_connected",
        translation_key="ocpp_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: _bool_field(d, "ocpp_connected", "connected"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="relay_enabled",
        translation_key="relay_enabled",
        value_fn=lambda d: _bool_field(d, "relay_enabled", "enabled"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="free_charging",
        translation_key="free_charging",
        value_fn=lambda d: _bool_field(d, "free_charging", "enabled"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="ground_monitoring_available",
        translation_key="ground_monitoring_available",
        value_fn=lambda d: _bool_field(d, "ground_monitoring_available", "available"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="calibration_law_available",
        translation_key="calibration_law_available",
        value_fn=lambda d: _bool_field(d, "calibration_law_available", "available"),
    ),
    ElliBinarySensorDescription(
        requires_auth=True,
        key="energy_saving_available",
        translation_key="energy_saving_available",
        value_fn=lambda d: _bool_field(d, "energy_saving_available", "available"),
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
    def available(self) -> bool:
        """Protected entities require configured credentials."""
        return super().available and (
            not self.entity_description.requires_auth
            or self.coordinator.api.authentication_enabled
        )

    @property
    def is_on(self) -> bool | None:
        """Return binary state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return vehicle details when available."""
        if self.entity_description.key != "vehicle_connected":
            return None

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
