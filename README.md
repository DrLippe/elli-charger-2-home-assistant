# Elli Charger 2 Home Assistant

Local Home Assistant custom integration for the **Elli Charger 2 Connect** using the charger's local REST API.

## Current scope

The integration is currently running in a temporary **unauthenticated-only mode**.

- UI config flow with IP/mDNS hostname only
- No username/password required
- No JWT login
- Only API endpoints that are reachable without authentication are queried
- Local polling via a Home Assistant `DataUpdateCoordinator`
- Live SSE listener on `/api/v2/events`
- Live charging power from `chargingCurvePointAppend`
- Charging state
- Vehicle connected state
- Last started charging session
- Charging authorization cause
- Charging energy
- Last charging start
- Lifetime energy and charging time
- Handles HTTP 204 as an empty/not-connected response

Authenticated configuration, diagnostics and control endpoints are intentionally disabled for now.

## Installation

Copy `custom_components/elli_charger_2` into your Home Assistant `custom_components` directory, or install the repository as a custom integration through HACS.

Restart Home Assistant and add **Elli Charger 2** through **Settings → Devices & services → Add integration**.

## Notes

The charger uses a local HTTPS endpoint. Certificate verification is currently disabled because local device certificates may not validate against Home Assistant's trust store.

API energy values are supplied in Wh and exposed as kWh where appropriate. Charging time is supplied in seconds.

This project is an independent community integration and is not affiliated with Elli.
