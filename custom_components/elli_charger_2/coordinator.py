"""DataUpdateCoordinator for Elli Charger 2."""

from __future__ import annotations

from datetime import timedelta
from math import isfinite
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from .api import ElliChargerApi, ElliChargerError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

# Curve events normally arrive about once per minute. Allow two missed intervals.
CHARGING_CURVE_MAX_AGE = 150


class ElliChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate REST updates for one charger."""

    def __init__(self, hass: HomeAssistant, api: ElliChargerApi, entry_id: str) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self._peak_store = Store(hass, 1, f"{DOMAIN}_session_peaks_{entry_id}")
        self._session_peaks: dict[str, float] = {}
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


    async def _record_peak(self, data: dict[str, Any]) -> None:
        """Retain the highest observed power per session across HA restarts."""
        session = data.get("last_session")
        if not isinstance(session, dict) or session.get("endDateTime"):
            return
        start = session.get("startDateTime")
        if not isinstance(start, str) or not start:
            return

        point = data.get("charging_curve_point")
        power: float | None = None
        if isinstance(point, dict):
            phases = [point.get(f"powerL{phase}") for phase in (1, 2, 3)]
            if all(type(value) in (int, float) and isfinite(value) and value >= 0 for value in phases):
                power = float(sum(phases))
        if power is None:
            rate = session.get("chargingRate")
            if type(rate) in (int, float) and isfinite(rate) and rate >= 0:
                power = float(rate)
        # Zero means idle/no usable peak; never treat it as a measured maximum.
        if power is None or power <= 0:
            return

        previous = self._session_peaks.get(start)
        if previous is None or power > previous:
            self._session_peaks[start] = power
            # Bound retained sessions; completed-session statistics are authoritative.
            if len(self._session_peaks) > 30:
                self._session_peaks = dict(list(self._session_peaks.items())[-30:])
            await self._peak_store.async_save(self._session_peaks)

    def _attach_session_metrics(self, data: dict[str, Any]) -> None:
        """Attach metrics from the latest completed session in charging statistics."""
        sessions = data.get("charging_statistic")
        if not isinstance(sessions, list):
            data["last_completed_metrics"] = None
            return
        valid = [item for item in sessions if isinstance(item, dict)
                 and isinstance(item.get("startDateTime"), str)
                 and isinstance(item.get("id"), (str, int))]
        if not valid:
            data["last_completed_metrics"] = None
            return
        # ISO timestamps are parsed by HA so offsets need not be identical.
        from homeassistant.util import dt as dt_util
        dated = [(dt_util.parse_datetime(s["startDateTime"]), s) for s in valid]
        dated = [(date, s) for date, s in dated if date is not None]
        if not dated:
            data["last_completed_metrics"] = None
            return
        session = max(dated, key=lambda item: item[0])[1]
        duration = session.get("duration")
        seconds = None
        if isinstance(duration, str):
            parts = duration.split(":")
            if len(parts) == 3:
                try:
                    h, m, s = map(int, parts)
                    if h >= 0 and 0 <= m < 60 and 0 <= s < 60:
                        seconds = h * 3600 + m * 60 + s
                except ValueError:
                    pass
        energy = session.get("energyConsumption")
        average = None
        if seconds and type(energy) in (int, float) and isfinite(energy) and energy >= 0:
            average = round(3.6 * energy / seconds, 3)
        peak = self._session_peaks.get(session["startDateTime"])
        data["last_completed_metrics"] = {
            "session_id": str(session["id"]),
            "start": session["startDateTime"],
            "duration_seconds": seconds,
            "average_power_kw": average,
            "observed_max_power_kw": round(peak, 3) if peak is not None else None,
        }

    async def async_setup(self) -> None:
        """Load static data and retained session peaks."""
        saved = await self._peak_store.async_load()
        if isinstance(saved, dict):
            self._session_peaks = {k: float(v) for k, v in saved.items()
                                   if isinstance(k, str) and type(v) in (int, float)
                                   and isfinite(v) and v >= 0}
        try:
            self.static_data = await self.api.async_get_static_data()
        except ElliChargerError:
            self.static_data = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.async_get_data()
            data = self._merge_curve_point(data)
            await self._record_peak(data)
            self._attach_session_metrics(data)
            return data
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
            await self._record_peak(data)
            self._attach_session_metrics(data)
            self.async_set_updated_data(data)
            return

        if event in {"deviceStateUpdate", "deviceTemperaturesUpdate"}:
            await self.async_request_refresh()
