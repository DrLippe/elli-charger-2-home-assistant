"""Local unauthenticated REST API client for Elli Charger 2 Connect."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout


class ElliChargerError(Exception):
    """Base exception for Elli Charger API errors."""


class ElliChargerConnectionError(ElliChargerError):
    """Raised when the charger cannot be reached."""


def normalize_host(host: str) -> str:
    """Return a normalized local charger base URL."""
    host = host.strip().rstrip("/")
    if "://" not in host:
        host = f"https://{host}"
    parsed = urlparse(host)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid host")
    return f"{parsed.scheme}://{parsed.netloc}"


class ElliChargerApi:
    """Async client for the unauthenticated local Charger 2 REST API."""

    def __init__(self, session: ClientSession, host: str) -> None:
        self._session = session
        self._base_url = normalize_host(host)
        self._event_task: asyncio.Task[None] | None = None
        self._event_stop = asyncio.Event()

    @property
    def base_url(self) -> str:
        """Return normalized base URL."""
        return self._base_url

    async def _request(self, method: str, path: str) -> Any:
        """Perform an unauthenticated API request."""
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                ssl=False,
                timeout=ClientTimeout(total=15),
            ) as response:
                if response.status == 204:
                    return None
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                text = await response.text()
                return text or None
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ElliChargerConnectionError(str(err)) from err

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch only endpoints that do not require authentication."""
        endpoints = {
            "charging_state": "/api/v2/charging/state",
            "last_session": "/api/v2/charging/last-started-session",
            "plugged_vehicle": "/api/v2/vehicles/plugged",
            "lifetime_stats": "/api/v2/charging/lifetime-stats",
            "energy_meter": "/api/v2/system/energy-meter",
        }

        async def fetch_optional(key: str, path: str) -> tuple[str, Any]:
            try:
                return key, await self._request("GET", path)
            except ElliChargerError:
                if key == "charging_state":
                    raise
                return key, None

        values = await asyncio.gather(
            *(fetch_optional(key, path) for key, path in endpoints.items())
        )
        return dict(values)

    async def async_get_static_data(self) -> dict[str, Any]:
        """Fetch unauthenticated static capability and setup information."""
        endpoints = {
            "language": "/api/v2/system/languages/selected",
            "onboarding": "/api/v2/system/onboarding",
            "country": "/api/v2/system/countries/selected",
            "max_current_required": "/api/v2/charging/max-current-per-phase/required",
            "phase_type_required": "/api/v2/charging/phase-type/required",
        }
        values = await asyncio.gather(
            *(self._request("GET", path) for path in endpoints.values())
        )
        return dict(zip(endpoints, values, strict=True))

    async def async_listen_events(
        self,
        callback: Callable[[str, Any | None], Awaitable[None]],
    ) -> None:
        """Listen to the unauthenticated SSE event stream."""
        self._event_stop.clear()
        while not self._event_stop.is_set():
            try:
                async with self._session.get(
                    f"{self._base_url}/api/v2/events",
                    headers={"Accept": "text/event-stream"},
                    ssl=False,
                    timeout=ClientTimeout(total=None, sock_read=90),
                ) as response:
                    response.raise_for_status()
                    event: str | None = None
                    data_lines: list[str] = []

                    async for raw_line in response.content:
                        if self._event_stop.is_set():
                            return

                        line = raw_line.decode(errors="ignore").rstrip("\r\n")

                        if not line:
                            if event is not None:
                                raw_data = "\n".join(data_lines)
                                payload: Any | None = None
                                if raw_data:
                                    try:
                                        payload = json.loads(raw_data)
                                    except json.JSONDecodeError:
                                        payload = raw_data
                                await callback(event, payload)
                            event = None
                            data_lines = []
                            continue

                        if line.startswith("event:"):
                            event = line.partition(":")[2].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line.partition(":")[2].lstrip())

            except (ClientError, asyncio.TimeoutError):
                if not self._event_stop.is_set():
                    await asyncio.sleep(5)

    def start_event_listener(
        self,
        callback: Callable[[str, Any | None], Awaitable[None]],
    ) -> None:
        """Start the background SSE listener."""
        if self._event_task is None or self._event_task.done():
            self._event_task = asyncio.create_task(self.async_listen_events(callback))

    async def async_stop_event_listener(self) -> None:
        """Stop the background SSE listener."""
        self._event_stop.set()
        if self._event_task is not None:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None
