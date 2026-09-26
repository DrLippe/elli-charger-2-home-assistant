"""Sensors for Elli Charger 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import ElliChargerEntity


@dataclass(frozen=True, kw_only=True)
class ElliSensorDescription(SensorEntityDescription):
    """Describe an Elli Charger sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _nested(data: dict[str, Any], group: str, key: str) -> Any:
    """Return one nested API value."""
    value = data.get(group)
    return value.get(key) if isinstance(value, dict) else None


def _wh_to_kwh(value: Any) -> float | None:
    """Convert API energy values from Wh to kWh."""
    if not isinstance(value, (int, float)) or value < 0:
        return None
    return round(value / 1000, 3)


def _format_duration(seconds: Any) -> str | None:
    """Format seconds as days, hours, minutes and seconds."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return None

    total_seconds = int(seconds)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} s")
    return " ".join(parts)


SENSORS: tuple[ElliSensorDescription, ...] = (
    ElliSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        value_fn=lambda d: _nested(d, "charging_state", "value"),
    ),
    ElliSensorDescription(
        key="max_current",
        translation_key="max_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda d: _nested(d, "charging_limits", "maxCurrent"),
    ),
    ElliSensorDescription(
        key="last_session_energy",
        translation_key="last_session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d: _wh_to_kwh(
            _nested(d, "last_session", "energyConsumption")
        ),
    ),
    ElliSensorDescription(
        key="last_session_charging_rate",
        translation_key="last_session_charging_rate",
        value_fn=lambda d: _nested(d, "last_session", "chargingRate"),
    ),
    ElliSensorDescription(
        key="lifetime_energy",
        translation_key="lifetime_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d: _wh_to_kwh(
            _nested(d, "lifetime_stats", "totalEnergy")
        ),
    ),
    ElliSensorDescription(
        key="lifetime_charging_time",
        translation_key="lifetime_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda d: _nested(d, "lifetime_stats", "totalChargingTime"),
    ),
    ElliSensorDescription(
        key="communication_controller_temperature",
        translation_key="communication_controller_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(
            d, "device_temperatures", "communicationControllerTemperature"
        ),
    ),
    ElliSensorDescription(
        key="emmc_temperature",
        translation_key="emmc_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(d, "device_temperatures", "eMmcTemperature"),
    ),
    ElliSensorDescription(
        key="input_path_temperature",
        translation_key="input_path_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(d, "device_temperatures", "inputPathTemperature"),
    ),
    ElliSensorDescription(
        key="output_path_temperature",
        translation_key="output_path_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(d, "device_temperatures", "outputPathTemperature"),
    ),
    ElliSensorDescription(
        key="power_controller_temperature",
        translation_key="power_controller_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(
            d, "device_temperatures", "powerControllerTemperature"
        ),
    ),
    ElliSensorDescription(
        key="relay_temperature",
        translation_key="relay_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _nested(d, "device_temperatures", "relayTemperature"),
    ),
    ElliSensorDescription(
        key="relay_state",
        translation_key="relay_state",
        value_fn=lambda d: _nested(d, "relay_state", "currentState"),
    ),
    ElliSensorDescription(
        key="active_errors",
        translation_key="active_errors",
        value_fn=lambda d: sum(
            1
            for error in (d.get("errors") or [])
            if isinstance(error, dict) and error.get("status") != "passive"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elli Charger sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ElliSensor(coordinator, entry.entry_id, description)
        for description in SENSORS
    )


class ElliSensor(ElliChargerEntity, SensorEntity):
    """Representation of an Elli Charger sensor."""

    entity_description: ElliSensorDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: ElliSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return useful diagnostic attributes."""
        if self.entity_description.key == "active_errors":
            return {"errors": self.coordinator.data.get("errors") or []}
        if self.entity_description.key == "relay_state":
            relay = self.coordinator.data.get("relay_state")
            return relay if isinstance(relay, dict) else None
        if self.entity_description.key == "lifetime_charging_time":
            seconds = _nested(
                self.coordinator.data,
                "lifetime_stats",
                "totalChargingTime",
            )
            return {
                "raw_seconds": seconds,
                "formatted_duration": _format_duration(seconds),
            }
        return None
