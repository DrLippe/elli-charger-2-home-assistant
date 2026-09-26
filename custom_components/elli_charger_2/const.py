"""Constants for the Elli Charger 2 integration."""

from homeassistant.const import Platform

DOMAIN = "elli_charger_2"

CONF_USER_TYPE = "user_type"

USER_TYPE_STANDARD = "standard"
USER_TYPE_SERVICE = "service"

API_USER_STANDARD = "standard"
API_USER_SERVICE = "technician"

DEFAULT_SCAN_INTERVAL = 10

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
