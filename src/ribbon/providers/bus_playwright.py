from __future__ import annotations

from datetime import datetime
from typing import Any

from ribbon.providers.base import BusProvider, ProviderError
from ribbon.providers.bus_darbi import filter_departures_for_stop, normalize_darbi_departures
from ribbon.settings import SETTINGS, SavedStop


class DarbiPlaywrightBusProvider(BusProvider):
    """Browser/XHR fallback for the Darbi departure widget."""

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_stop(self, stop: SavedStop, now: datetime):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - optional runtime
            raise ProviderError(f"Playwright import failed: {exc}") from exc

        captured_payloads: list[dict[str, Any]] = []
        try:  # pragma: no cover - exercised as browser fallback integration
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})

                def on_response(response) -> None:
                    if "MMJPv5/BusStopDepartureBoard" not in response.url:
                        return
                    try:
                        payload = response.json()
                    except Exception:
                        return
                    if isinstance(payload, dict) and payload.get("Departures"):
                        captured_payloads.append(payload)

                page.on("response", on_response)
                page.goto(SETTINGS.darbi_map_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(4_000)
                page.evaluate(
                    """
                    (stopId) => {
                      const departures = window.bindingObj?.bus_tabs?.mmjp_departures;
                      if (!departures || typeof departures.search !== "function") {
                        throw new Error("Darbi mmjp_departures widget not available");
                      }
                      if (typeof departures.isWidget === "function") {
                        departures.isWidget(false);
                      }
                      departures.search(stopId);
                    }
                    """,
                    stop.stop_id,
                )
                page.wait_for_timeout(4_000)

                raw_items: list[dict[str, Any]] = []
                for payload in captured_payloads:
                    filtered = filter_departures_for_stop(payload.get("Departures", []), stop.stop_id)
                    if filtered:
                        raw_items = filtered
                        break

                if not raw_items:
                    fallback_rows = page.evaluate(
                        """
                        () => {
                          const rows = [];
                          const list = window.bindingObj?.bus_tabs?.mmjp_departures?.list?.() || [];
                          for (const stopBoard of list) {
                            const departures = stopBoard.departures || [];
                            for (const departure of departures) {
                              rows.push({
                                line: departure.line || null,
                                direction: departure.direction || null,
                                time: departure.time || null,
                                isRealtime: !!departure.isRealtime,
                                stopId: stopBoard.id || null,
                                stopCode: stopBoard.displayID || stopBoard.stopId || null,
                              });
                            }
                          }
                          return rows;
                        }
                        """
                    )
                    raw_items = filter_departures_for_stop(fallback_rows, stop.stop_id)
                browser.close()
        except Exception as exc:
            raise ProviderError(f"Playwright browser/XHR fallback failed: {exc}") from exc

        normalized = normalize_darbi_departures(raw_items, stop, now, source="darbi-browser-xhr")
        if not normalized:
            raise ProviderError(f"Playwright fallback returned no usable departures for {stop.stop_id}")
        return normalized
