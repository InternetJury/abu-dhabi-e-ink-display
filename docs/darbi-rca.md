# Darbi Live Feed RCA

Date verified: April 4, 2026

## Root Cause

Blank live bus boards were caused by provider failures, not by the renderer.

The old live path guessed outdated or malformed Darbi endpoints:

- malformed `MMJPv3` proxy URL returned `400`
- alternate `MMJPv3` controller path returned `404`
- `api/bus/MonitorStop` returned `401`

The browser fallback also failed because it only scraped static rows and never opened the real departures widget or captured its XHR traffic.

## Working Live Path

The current Darbi web app uses the proxy-wrapped MMJPv5 stop-departure search:

`https://darbi.itc.gov.ae/dotservices/proxyAPI/proxy.ashx?https://darbi.itc.gov.ae/dotservices/api/MMJPv5/BusStopDepartureBoard?&text=<STOP_CODE>&direct=true&info=&limit=0&language=en`

Verified example:

`...MMJPv5/BusStopDepartureBoard?&text=00513B&direct=true&info=&limit=0&language=en`

This returns `200` and a payload containing `Departures` plus per-item `Stop`, `Line`, `Remaining`, `Time`, `Realtime`, and related fields.

## Important Detail

The MMJPv5 response can include multiple nearby platform variants. The production provider must filter exact rows using the public stop code in `Stop.StopID`, for example `00513B`.

The payload also exposes an internal numeric stop id such as `1000513`, but that is not required for the primary live board fetch once the MMJPv5 stop-code search is used correctly.

## Production Recovery Strategy

1. Direct live fetch through MMJPv5 using the public stop code.
2. Exact `Stop.StopID` filtering on the returned departures.
3. Browser/XHR fallback by invoking the real Darbi widget search and capturing the MMJPv5 network response.
4. Last-good cache fallback with a stale timestamp if live fetches fail.

## Visible Product Behavior

- Fresh live departures render normally when MMJPv5 succeeds.
- If Darbi fails temporarily, the ribbon renders the last-good cached board instead of a blank panel.
- RCA logs are written to `output/cache/darbi_rca.jsonl`.
