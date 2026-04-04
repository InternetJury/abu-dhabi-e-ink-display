from __future__ import annotations

from datetime import datetime

from ribbon.derive.insights import build_multi_stop_snapshot, build_stop_insight
from ribbon.models import CityPulseSummary, MarketIndexItem, ModeName, RefreshHint, RibbonSnapshot, WeatherSummary
from ribbon.providers import BusProvider, HeadlineProvider, MarketProvider, ProviderError, WeatherProvider
from ribbon.settings import SETTINGS, SavedStop


def _fallback_weather(now: datetime, note: str = "Unavailable") -> WeatherSummary:
    return WeatherSummary(
        location_label=SETTINGS.weather_location_label,
        temperature_c=0.0,
        daily_high_c=None,
        daily_low_c=None,
        condition_label=note,
        humidity_pct=None,
        aqi_index=None,
        aqi_label=None,
        sunrise_local=None,
        sunset_local=None,
        observed_at=now,
    )


def _bus_provider_note(bus_provider: BusProvider, stop_id: str) -> str | None:
    getter = getattr(bus_provider, "get_last_status", None)
    if not callable(getter):
        return None
    status = getter(stop_id)
    if status is None:
        return None
    note = status.note()
    if note:
        return note
    if status.source == "darbi-browser-xhr":
        return "Using Darbi browser/XHR recovery path."
    return None


def build_city_summary(mode: ModeName, primary_stop, multi_stop=None) -> CityPulseSummary:
    if mode == ModeName.WEEKEND_MULTI_STOP and multi_stop is not None:
        live_counts = sum(1 for stop in multi_stop.stops if stop.hero is not None)
        return CityPulseSummary(
            summary_line=f"{live_counts}/{len(multi_stop.stops)} saved stops currently show upcoming service.",
            detail_lines=[
                f"{stop.stop_title}: {stop.hero.due_label if stop.hero else 'No live board'}"
                for stop in multi_stop.stops[:4]
            ],
        )

    if primary_stop is None or primary_stop.hero is None:
        return CityPulseSummary(
            summary_line="Mobility feed quiet or unavailable right now",
            detail_lines=["Renderer remains live with utility context intact."],
        )

    if primary_stop.irregularity_summary:
        summary_line = f"Mobility note: {primary_stop.irregularity_summary[0]}."
    else:
        summary_line = (
            f"Next {primary_stop.hero.route_number} to {primary_stop.hero.destination} "
            f"in {primary_stop.hero.due_label.lower()}."
        )
    detail_lines = []
    return CityPulseSummary(summary_line=summary_line, detail_lines=detail_lines)


def build_live_snapshot(
    *,
    mode: ModeName,
    now: datetime,
    refresh_hint: RefreshHint,
    bus_provider: BusProvider,
    weather_provider: WeatherProvider,
    headline_provider: HeadlineProvider,
    market_provider: MarketProvider | None = None,
) -> RibbonSnapshot:
    degraded_notes: list[str] = []
    try:
        weather = weather_provider.fetch(now)
    except ProviderError as exc:
        weather = _fallback_weather(now)
        degraded_notes.append(f"Weather unavailable: {exc}")

    try:
        headlines = headline_provider.fetch(limit=6)
    except ProviderError as exc:
        headlines = []
        degraded_notes.append(f"Headlines unavailable: {exc}")

    market_indices: list[MarketIndexItem] = []
    if market_provider is not None:
        try:
            market_indices = market_provider.fetch(now)
        except ProviderError as exc:
            degraded_notes.append(f"Markets unavailable: {exc}")

    primary_stop = None
    multi_stop = None
    if mode == ModeName.WEEKEND_MULTI_STOP:
        departures_by_stop: dict[str, list] = {}
        for stop in SETTINGS.weekend_stops:
            try:
                departures_by_stop[stop.stop_id] = bus_provider.fetch_stop(stop, now)
                provider_note = _bus_provider_note(bus_provider, stop.stop_id)
                if provider_note:
                    degraded_notes.append(f"{stop.title}: {provider_note}")
            except ProviderError as exc:
                departures_by_stop[stop.stop_id] = []
                degraded_notes.append(f"{stop.title}: {exc}")
        multi_stop = build_multi_stop_snapshot(
            list(SETTINGS.weekend_stops),
            departures_by_stop,
            now,
            SETTINGS.walking_buffer_minutes,
        )
        city_summary = build_city_summary(mode, None, multi_stop)
    else:
        stop: SavedStop = SETTINGS.weekday_commute_stop
        try:
            departures = bus_provider.fetch_stop(stop, now)
            provider_note = _bus_provider_note(bus_provider, stop.stop_id)
            if provider_note:
                degraded_notes.append(f"{stop.title}: {provider_note}")
        except ProviderError as exc:
            departures = []
            degraded_notes.append(f"{stop.title}: {exc}")
        primary_stop = build_stop_insight(stop, departures, now, SETTINGS.walking_buffer_minutes)
        city_summary = build_city_summary(mode, primary_stop)

    return RibbonSnapshot(
        mode=mode,
        generated_at=now,
        timezone=SETTINGS.timezone,
        refresh_hint=refresh_hint,
        weather=weather,
        headlines=headlines,
        market_indices=market_indices,
        primary_stop=primary_stop,
        multi_stop=multi_stop,
        city_summary=city_summary,
        degraded_reason=" | ".join(degraded_notes) if degraded_notes else None,
    )
