"""DataUpdateCoordinator for Elli Charger 2."""

from __future__ import annotations

from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ElliChargerApi, ElliChargerError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

# Curve events normally arrive about once per minute. Allow two missed intervals.
CHARGING_CURVE_MAX_AGE = 150


class ElliChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate REST updates for one charger."""

    def __init__(self, hass: HomeAssistant, api: ElliChargerApi) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.static_data: dict[str, Any] = {}
        self._curve_point: dict[str, Any] | None = None
        self._curve_received_at: float | None = None

    def _clear_curve_point(self) -> None:
        """Discard a point that no longer belongs to an active session."""
        self._curve_point = None
        self._curve_received_at = None

    def _merge_curve_point(self, data: dict[str, Any]) -> dict[str, Any]:
        """Preserve SSE power samples across REST polls for a bounded time."""
        previous_session = (self.data or {}).get("last_session")
        session = data.get("last_session")
        if isinstance(session, dict):
            if session.get("endDateTime"):
                self._clear_curve_point()
            elif isinstance(previous_session, dict):
                previous_start = previous_session.get("startDateTime")
                current_start = session.get("startDateTime")
                if previous_start and current_start and previous_start != current_start:
                    self._clear_curve_point()

        if self._curve_received_at is not None:
            if monotonic() - self._curve_received_at >= CHARGING_CURVE_MAX_AGE:
                self._clear_curve_point()
            elif self._curve_point is not None:
                data["charging_curve_point"] = self._curve_point
        return data

    async def async_setup(self) -> None:
        """Load static data once."""
        try:
            self.static_data = await self.api.async_get_static_data()
        except ElliChargerError:
            self.static_data = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.async_get_data()
            return self._merge_curve_point(data)
        except ElliChargerError as err:
            raise UpdateFailed(str(err)) from err

    async def async_event_refresh(
        self,
        event: str,
        payload: Any | None,
    ) -> None:
        """Handle live SSE updates from the charger."""
        if event == "chargingCurvePointAppend" and isinstance(payload, dict):
            self._curve_point = payload
            self._curve_received_at = monotonic()
            data = dict(self.data or {})
            data["charging_curve_point"] = payload
            self.async_set_updated_data(data)
            return

        if event in {"deviceStateUpdate", "deviceTemperaturesUpdate"}:
            await self.async_request_refresh()
