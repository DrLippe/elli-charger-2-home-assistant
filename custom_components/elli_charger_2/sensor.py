"""Sensors for Elli Charger 2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import ElliChargerEntity


@dataclass(frozen=True, kw_only=True)
class ElliSensorDescription(SensorEntityDescription):
    """Describe an Elli Charger sensor."""

    requires_auth: bool = False
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


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp returned by the charger."""
    if not isinstance(value, str) or not value:
        return None
    return dt_util.parse_datetime(value)


def _format_duration(seconds: Any) -> str | None:
    """Format seconds as days, hours and minutes."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return None

    total_seconds = int(seconds)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    parts: list[str] = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes or not parts:
        parts.append(f"{minutes} min")
    return " ".join(parts)


def _last_session_date(data: dict[str, Any]) -> date | None:
    """Return the last session's start date in Home Assistant's time zone."""
    started = _parse_datetime(_nested(data, "last_session", "startDateTime"))
    if started is None or started.tzinfo is None:
        return None
    return dt_util.as_local(started).date()


def _authorization_cause(data: dict[str, Any]) -> str | None:
    """Return the authorization cause of the last started session."""
    cause = _nested(data, "last_session", "authorizationCause")
    return str(cause) if cause not in (None, "") else None


def _latest_curve_point(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the latest live charging-curve point."""
    point = data.get("charging_curve_point")
    return point if isinstance(point, dict) else None


def _charging_power(data: dict[str, Any]) -> float | None:
    """Return current total charging power in kW."""
    if _nested(data, "last_session", "endDateTime"):
        return 0
    point = _latest_curve_point(data)
    if point is not None:
        phases = [point.get("powerL1"), point.get("powerL2"), point.get("powerL3")]
        if all(isinstance(value, (int, float)) for value in phases):
            return round(sum(phases), 3)

    # Fallback for devices/firmware that do not expose the charging curve.
    rate = _nested(data, "last_session", "chargingRate")
    if isinstance(rate, (int, float)) and rate >= 0:
        return rate
    return None


SENSORS: tuple[ElliSensorDescription, ...] = (
    ElliSensorDescription(
        key="last_charging_session",
        translation_key="last_charging_session",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:ev-plug-type2",
        value_fn=_last_session_date,
    ),
    ElliSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        icon="mdi:ev-station",
        value_fn=lambda d: _nested(d, "charging_state", "value"),
    ),
    ElliSensorDescription(
        key="rfid_card",
        translation_key="authorization_cause",
        icon="mdi:card-account-details-outline",
        value_fn=_authorization_cause,
    ),
    ElliSensorDescription(
        key="last_session_charging_rate",
        translation_key="last_session_charging_rate",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_fn=_charging_power,
    ),
    ElliSensorDescription(
        key="last_session_energy",
        translation_key="last_session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:battery-charging",
        value_fn=lambda d: _wh_to_kwh(
            _nested(d, "last_session", "energyConsumption")
        ),
    ),
    ElliSensorDescription(
        key="last_charging_start",
        translation_key="last_charging_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=lambda d: _parse_datetime(
            _nested(d, "last_session", "startDateTime")
        ),
    ),
    ElliSensorDescription(
        key="lifetime_energy",
        translation_key="lifetime_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _wh_to_kwh(
            _nested(d, "lifetime_stats", "totalEnergy")
        ),
    ),
    ElliSensorDescription(
        key="lifetime_charging_time",
        translation_key="lifetime_charging_time",
        icon="mdi:timer-outline",
        value_fn=lambda d: _format_duration(
            _nested(d, "lifetime_stats", "totalChargingTime")
        ),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="max_current",
        translation_key="max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(d, "charging_limits", "maxCurrent"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="communication_controller_temperature",
        translation_key="communication_controller_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(
            d, "device_temperatures", "communicationControllerTemperature"
        ),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="emmc_temperature",
        translation_key="emmc_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(d, "device_temperatures", "eMmcTemperature"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="input_path_temperature",
        translation_key="input_path_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(d, "device_temperatures", "inputPathTemperature"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="output_path_temperature",
        translation_key="output_path_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(d, "device_temperatures", "outputPathTemperature"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="power_controller_temperature",
        translation_key="power_controller_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(
            d, "device_temperatures", "powerControllerTemperature"
        ),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="relay_temperature",
        translation_key="relay_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _nested(d, "device_temperatures", "relayTemperature"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="relay_state",
        translation_key="relay_state",
        value_fn=lambda d: _nested(d, "relay_state", "currentState"),
    ),
    ElliSensorDescription(
        requires_auth=True,
        key="active_errors",
        translation_key="active_errors",
        value_fn=lambda d: sum(
            1
            for error in d["errors"]
            if isinstance(error, dict) and error.get("status") != "passive"
        ) if isinstance(d.get("errors"), list) else None,
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
    def available(self) -> bool:
        """Protected entities require configured credentials."""
        return super().available and (
            not self.entity_description.requires_auth
            or self.coordinator.api.authentication_enabled
        )

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return useful diagnostic attributes."""
        if self.entity_description.key == "last_charging_session":
            session = self.coordinator.data.get("last_session")
            return session if isinstance(session, dict) else None
        if self.entity_description.key == "last_session_charging_rate":
            point = _latest_curve_point(self.coordinator.data)
            if point is None:
                return {"source": "last_started_session.chargingRate"}
            return {
                "source": "charging_curve",
                "power_l1_kw": point.get("powerL1"),
                "power_l2_kw": point.get("powerL2"),
                "power_l3_kw": point.get("powerL3"),
                "timestamp": point.get("timestamp"),
            }
        if self.entity_description.key == "rfid_card":
            session = self.coordinator.data.get("last_session")
            if isinstance(session, dict):
                return {
                    "authorization_cause": session.get("authorizationCause"),
                    "session_start": session.get("startDateTime"),
                }
            return None
        if self.entity_description.key == "active_errors":
            return {"errors": self.coordinator.data.get("errors")}
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
