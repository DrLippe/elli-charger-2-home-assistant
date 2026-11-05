"""Local REST API client for Elli Charger 2 Connect."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_USER_SERVICE, API_USER_STANDARD, USER_TYPE_SERVICE


class ElliChargerError(Exception):
    """Base exception for Elli Charger API errors."""


class ElliChargerConnectionError(ElliChargerError):
    """Raised when the charger cannot be reached."""


class ElliChargerAuthenticationError(ElliChargerError):
    """Raised when authentication fails."""


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
    """Async client for the local Elli Charger 2 REST API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        user_type: str = "standard",
        password: str = "",
    ) -> None:
        self._session = session
        self._base_url = normalize_host(host)
        self._user_type = user_type
        self._password = password
        self._token: str | None = None
        self._login_lock = asyncio.Lock()
        self._event_task: asyncio.Task[None] | None = None
        self._event_stop = asyncio.Event()

    @property
    def base_url(self) -> str:
        """Return normalized base URL."""
        return self._base_url

    @property
    def authentication_enabled(self) -> bool:
        """Only use protected endpoints when a password was supplied."""
        return bool(self._password)

    @property
    def api_user(self) -> str:
        """Return API username for configured account type."""
        return API_USER_SERVICE if self._user_type == USER_TYPE_SERVICE else API_USER_STANDARD

    async def async_login(self) -> None:
        """Authenticate and cache the JWT in memory."""
        if not self.authentication_enabled:
            raise ElliChargerAuthenticationError("No credentials configured")
        try:
            async with self._session.post(
                f"{self._base_url}/api/v2/jwt/login",
                data={"user": self.api_user, "pass": self._password},
                ssl=False,
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status in (401, 403):
                    raise ElliChargerAuthenticationError("Invalid credentials")
                response.raise_for_status()
                payload = await response.json()
        except ElliChargerAuthenticationError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ElliChargerConnectionError(str(err)) from err

        token = payload.get("token") if isinstance(payload, dict) else None
        if not token:
            raise ElliChargerAuthenticationError("Login response did not contain a token")
        self._token = str(token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        retry_auth: bool = True,
        json_body: Any = None,
    ) -> Any:
        if auth:
            if not self.authentication_enabled:
                raise ElliChargerAuthenticationError("No credentials configured")
            async with self._login_lock:
                if not self._token:
                    await self.async_login()

        headers = {"Authorization": f"Bearer {self._token}"} if auth else {}
        request_token = self._token
        try:
            request_options = {
                "headers": headers,
                "ssl": False,
                "timeout": ClientTimeout(total=15),
            }
            if json_body is not None:
                request_options["json"] = json_body
            async with self._session.request(
                method, f"{self._base_url}{path}", **request_options
            ) as response:
                if response.status == 401 and auth and retry_auth:
                    # Concurrent polls must share one renewed token. A 403 is a
                    # permission failure and must not cause repeated logins.
                    async with self._login_lock:
                        if self._token == request_token:
                            await self.async_login()
                    return await self._request(
                        method, path, auth=True, retry_auth=False,
                        json_body=json_body,
                    )
                if response.status in (401, 403):
                    raise ElliChargerAuthenticationError("Authentication rejected")
                if response.status == 204:
                    return None
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                text = await response.text()
                return text or None
        except ElliChargerAuthenticationError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ElliChargerConnectionError(str(err)) from err

    async def async_check_token(self) -> Any:
        """Check the active local JWT (requires configured credentials)."""
        return await self._request("GET", "/api/v2/jwt/check", auth=True)

    async def async_logout(self) -> Any:
        """End the local JWT session and discard the cached token."""
        if not self._token:
            return None
        try:
            return await self._request(
                "POST", "/api/v2/jwt/logout", auth=True, retry_auth=False
            )
        finally:
            self._token = None

    async def async_get_charging_curve(self) -> Any:
        """Fetch the charging curve as a REST snapshot (SSE remains preferred)."""
        return await self._request("GET", "/api/v2/dashboard/charging-curve", auth=True)

    async def async_put_charging_setting(self, setting: str, payload: Any) -> Any:
        """Send a local firmware PUT with a caller-supplied, verified JSON body.

        No assumptions are made about the firmware's body schema. This method is
        intentionally not exposed as a Home Assistant action until those schemas
        have been validated against the charger.
        """
        paths = {
            "direct_authorization": "/api/v2/charging/direct-authorization",
            "free_charging": "/api/v2/charging/free-charging",
            "user_limit_current": "/api/v2/charging/user-limit-current",
            "user_limit_power": "/api/v2/charging/user-limit-power",
            "limits": "/api/v2/charging/limits",
            "ocpp_remote_start_enabled": (
                "/api/v2/connection/ocpp/remote-start-charging-enabled"
            ),
        }
        if setting not in paths:
            raise ValueError(f"Unsupported local charging setting: {setting}")
        if payload is None:
            raise ValueError("An explicit JSON payload is required")
        return await self._request("PUT", paths[setting], auth=True, json_body=payload)

    @staticmethod
    def _integer_value(value: int) -> int:
        """Ensure JSON integers cannot silently truncate floats or booleans."""
        if type(value) is not int or value < 0:
            raise ValueError("Expected a non-negative integer")
        return value

    @staticmethod
    def _enabled_value(enabled: bool) -> dict[str, bool]:
        """Build the firmware's Enabled model."""
        if type(enabled) is not bool:
            raise ValueError("Expected a boolean")
        return {"enabled": enabled}

    async def async_set_direct_authorization(self, allow: bool) -> Any:
        """Set the firmware's allow/deny direct authorization mode."""
        if type(allow) is not bool:
            raise ValueError("Expected a boolean")
        return await self.async_put_charging_setting(
            "direct_authorization", {"value": "allow" if allow else "deny"}
        )

    async def async_set_free_charging(self, enabled: bool) -> Any:
        """Set free charging (technician permission required)."""
        return await self.async_put_charging_setting(
            "free_charging", self._enabled_value(enabled)
        )

    async def async_set_user_limit_current(self, value: int) -> Any:
        """Set the user current limit with the firmware's Current model."""
        return await self.async_put_charging_setting(
            "user_limit_current", {"value": self._integer_value(value)}
        )

    async def async_set_user_limit_power(self, value: int) -> Any:
        """Set the user power limit with the firmware's Power model."""
        return await self.async_put_charging_setting(
            "user_limit_power", {"value": self._integer_value(value)}
        )

    async def async_set_charging_limits(
        self, max_power: float, max_current: int
    ) -> Any:
        """Set the firmware's ChargingLimits model.

        Units and hardware-specific acceptable ranges require live validation.
        """
        if (type(max_power) not in (int, float)
                or not math.isfinite(max_power) or max_power < 0):
            raise ValueError("Expected a finite non-negative maximum power")
        return await self.async_put_charging_setting(
            "limits", {
                "maxPower": float(max_power),
                "maxCurrent": self._integer_value(max_current),
            }
        )

    async def async_set_ocpp_remote_start_enabled(self, enabled: bool) -> Any:
        """Set OCPP remote-start capability (technician permission required)."""
        return await self.async_put_charging_setting(
            "ocpp_remote_start_enabled", self._enabled_value(enabled)
        )

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch the current state used by Home Assistant entities."""
        endpoints: dict[str, tuple[str, bool]] = {
            "charging_state": ("/api/v2/charging/state", False),
            "last_session": ("/api/v2/charging/last-started-session", False),
            "plugged_vehicle": ("/api/v2/vehicles/plugged", False),
            "lifetime_stats": ("/api/v2/charging/lifetime-stats", False),
            # Additional read routes identified in Elli firmware. Their response
            # schemas vary by firmware, so expose raw values in diagnostics first.
            "charging_statistic": ("/api/v2/charging/statistic", True),
            "charging_user_limit_current": ("/api/v2/charging/user-limit-current", True),
            "charging_user_limit_power": ("/api/v2/charging/user-limit-power", True),
            "charging_direct_authorization": ("/api/v2/charging/direct-authorization", True),
            "ocpp_remote_start_enabled": (
                "/api/v2/connection/ocpp/remote-start-charging-enabled", True
            ),
            "energy_meter": ("/api/v2/system/energy-meter", False),
            "ethernet_connected": ("/api/v2/connection/ethernet/connected", True),
            "network_connected": ("/api/v2/connection/network/connected", True),
            "wlan_connected": ("/api/v2/connection/wlan-client/connected", True),
            "lte_connected": ("/api/v2/connection/lte/connected", True),
            "lte_status": ("/api/v2/connection/lte/status", True),
            "ocpp": ("/api/v2/connection/ocpp", True),
            "ocpp_enabled": ("/api/v2/connection/ocpp/enabled", True),
            "ocpp_connected": ("/api/v2/connection/ocpp/connected", True),
            "eebus_paired": ("/api/v2/connection/eebus/paired", True),
            "charging_limits": ("/api/v2/charging/limits", True),
            "relay_state": ("/api/v2/system/relais-switch/state", True),
            "relay_enabled": ("/api/v2/system/relais-switch/enabled", True),
            "free_charging": ("/api/v2/charging/free-charging", True),
            "errors": ("/api/v2/system/errors", True),
            "restrictions": ("/api/v2/charging/restrictions", True),
            "update_info": ("/api/v2/system/update/info", True),
            "ground_monitoring_available": (
                "/api/v2/system/ground-monitoring/available",
                True,
            ),
            "calibration_law_available": (
                "/api/v2/system/enable-calibration-law/available",
                True,
            ),
            "energy_saving_available": (
                "/api/v2/system/energy-saving/available",
                True,
            ),
            "device_state": ("/api/v2/system/device-state", True),
            "device_temperatures": ("/api/v2/system/device-temperatures", True),
        }

        # The unauthenticated charging state is our connectivity baseline.
        # Additional authenticated endpoints may be unavailable for the standard
        # account or on hardware variants, so they must not take down the whole
        # integration.
        charging_state = await self._request(
            "GET", "/api/v2/charging/state", auth=False
        )

        async def fetch_optional(key: str, path: str, auth: bool) -> tuple[str, Any]:
            if key == "charging_state":
                return key, charging_state
            if auth and not self.authentication_enabled:
                return key, None
            try:
                return key, await self._request("GET", path, auth=auth)
            except ElliChargerError:
                return key, None

        values = await asyncio.gather(
            *(
                fetch_optional(key, path, auth)
                for key, (path, auth) in endpoints.items()
            )
        )
        return dict(values)

    async def async_get_static_data(self) -> dict[str, Any]:
        """Fetch mostly static capability and setup information."""
        endpoints = {
            "language": "/api/v2/system/languages/selected",
            "onboarding": "/api/v2/system/onboarding",
            "country": "/api/v2/system/countries/selected",
            "max_current_required": "/api/v2/charging/max-current-per-phase/required",
            "phase_type_required": "/api/v2/charging/phase-type/required",
        }
        values = await asyncio.gather(
            *(self._request("GET", path, auth=False) for path in endpoints.values())
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
