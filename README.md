# Elli Charger 2 Home Assistant

Local Home Assistant custom integration for the **Elli Charger 2 Connect** using the charger's local REST API.

## Current scope

- UI config flow with IP/mDNS hostname
- Standard user (`standard`) or service user (`technician`)
- JWT authentication via `POST /api/v2/jwt/login`
- Automatic re-login on an expired/rejected JWT
- Local polling via a Home Assistant `DataUpdateCoordinator`
- SSE listener on `/api/v2/events` to trigger fast refreshes for device state and temperature updates
- Charging state, limits, lifetime/session values, temperatures and relay state
- Ethernet/network/WLAN/LTE, OCPP and capability binary sensors
- Handles HTTP 204 as an unavailable/not-connected value instead of an API error

## Installation

Copy `custom_components/elli_charger_2` into your Home Assistant `custom_components` directory, or install the repository as a custom integration through HACS.

Restart Home Assistant and add **Elli Charger 2** through **Settings → Devices & services → Add integration**.

## Notes

The charger uses a local HTTPS endpoint. Certificate verification is currently disabled because local device certificates may not validate against Home Assistant's trust store.

Energy/rate values whose unit has not yet been confirmed from the device API are intentionally exposed without a Home Assistant unit/device class for now.

This project is an independent community integration and is not affiliated with Elli.
