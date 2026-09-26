"""DataUpdateCoordinator for Elli Charger 2."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ElliChargerApi, ElliChargerError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN


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

    async def async_setup(self) -> None:
        """Load static data once."""
        try:
            self.static_data = await self.api.async_get_static_data()
        except ElliChargerError:
            self.static_data = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_data()
        except ElliChargerError as err:
            raise UpdateFailed(str(err)) from err

    async def async_event_refresh(self, _event: str) -> None:
        """Refresh coordinator after a relevant SSE event."""
        await self.async_request_refresh()
