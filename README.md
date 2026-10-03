# Elli Charger 2 Home Assistant

Local Home Assistant custom integration for the **Elli Charger 2 Connect** using the charger's local REST API.

## Current scope

Authentication is optional. Leave the password empty to use public REST endpoints and live SSE charging data. Supply the standard-user or service-user password to enable protected data. The service-user API login is `technician`; the standard-user login is `standard`.

- UI config flow with IP/mDNS hostname and optional user type/password
- JWT login and token renewal only when credentials are supplied
- Protected endpoints are skipped entirely without credentials
- Optional credentials can be added, changed or removed through integration options
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

With authentication, the previously disabled sensors are restored: maximum current, six device temperatures, relay state, active errors, Ethernet/network/WLAN/LTE connectivity, OCPP enabled/connected, phase switching enabled, free charging, and ground-monitoring/calibration-law/energy-saving capabilities. Protected OCPP configuration, LTE status, EEBUS pairing, charging restrictions, firmware/update information and device state are also fetched for diagnostics.

These are monitoring entities; this integration does not write settings or issue charging commands. Protected entities are unavailable without credentials. Missing or forbidden protected data is unknown, never a fabricated zero or disconnected state. Individual unsupported or forbidden endpoints do not interrupt public data. Tokens stay in memory; diagnostic exports redact credentials, including integration options.

## Installation

Copy `custom_components/elli_charger_2` into your Home Assistant `custom_components` directory, or install the repository as a custom integration through HACS.

Restart Home Assistant and add **Elli Charger 2** through **Settings → Devices & services → Add integration**.

For an existing installation, open **Settings → Devices & services → Elli Charger 2 → Configure** to set the optional credentials. Enter the password whenever saving authentication options. Leaving the password empty disables authentication, including credentials stored by older versions. Saving reloads the integration automatically.

## Notes

The charger uses a local HTTPS endpoint. Certificate verification is currently disabled because local device certificates may not validate against Home Assistant's trust store.

API energy values are supplied in Wh and exposed as kWh where appropriate.

Charging-curve samples arrive via SSE roughly every 60 seconds. The latest sample is retained across REST polls for up to 150 seconds, then the integration falls back to the session's charging rate. A changed session start or an explicit session end clears the cached sample.

Lifetime charging time is displayed as days, hours and minutes (for example `2 d 5 h 12 min`); the original seconds remain available in the `raw_seconds` attribute. This display sensor no longer has a numeric state or statistics. Existing statistics from earlier versions are not converted.

Last charging session shows the date of the last session start in Home Assistant's configured time zone. Last charging start continues to expose the full timestamp. No recorded session is shown as unknown.

This project is an independent community integration and is not affiliated with Elli.

## Validation

Run `python -m unittest discover -s tests -v` for isolated regression tests of charging data, public/protected requests and credential handling. These tests do not require Home Assistant or a wallbox; hardware validation remains necessary.
