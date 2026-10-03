"""Diagnostics support for Elli Charger 2."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# Keep redaction for credentials from config entries created by older versions.
TO_REDACT = {"password", "token", "backendUsername", "backendPassword", "access_token", "refresh_token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "static_data": async_redact_data(coordinator.static_data, TO_REDACT),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
