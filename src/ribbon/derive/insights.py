from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from ribbon.models import (
    BusDepartureItem,
    FrequencyBand,
    LeaveByRecommendation,
    LeaveByStatus,
    MultiStopSnapshot,
    NextBusHero,
    RouteFrequencySummary,
    ServiceDensityWindow,
    StopInsightSnapshot,
)
from ribbon.settings import SavedStop


def _format_due_label(item: BusDepartureItem) -> str:
    if item.due_minutes is None and item.expected_at is None:
        return "No ETA"
    due = item.due_minutes if item.due_minutes is not None else 0
    if due <= 0:
        return "Due"
    return f"{due:02d} min"


def _format_time_label(value: datetime | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def derive_next_bus_hero(departures: list[BusDepartureItem], stop: SavedStop) -> NextBusHero | None:
    if not departures:
        return None
    next_departure = departures[0]
    confidence = "live" if next_departure.is_live else "scheduled"
    return NextBusHero(
        stop_id=stop.stop_id,
        route_number=next_departure.route_number,
        destination=next_departure.destination,
        due_label=_format_due_label(next_departure),
        scheduled_label=_format_time_label(next_departure.expected_at or next_departure.scheduled_at),
        confidence_label=confidence,
        irregularity_flag=next_departure.marker,
    )


def derive_service_density(departures: list[BusDepartureItem], now: datetime) -> ServiceDensityWindow:
    window_end = now + timedelta(minutes=60)
    bins = [0, 0, 0, 0]
    routes = set()
    count = 0
    for departure in departures:
        departure_time = departure.expected_at or departure.scheduled_at
        if departure_time is None or departure_time < now or departure_time > window_end:
            continue
        count += 1
        routes.add(departure.route_number)
        delta = int((departure_time - now).total_seconds() // 60)
        index = min(delta // 15, 3)
        bins[index] += 1
    return ServiceDensityWindow(
        window_start=now,
        window_end=window_end,
        departures_count=count,
        routes_active=len(routes),
        bins=bins,
    )


def _band_for_spacing(spacing: int | None) -> FrequencyBand:
    if spacing is None:
        return FrequencyBand.UNKNOWN
    if spacing <= 8:
        return FrequencyBand.FREQUENT
    if spacing <= 18:
        return FrequencyBand.MODERATE
    return FrequencyBand.SPARSE


def derive_route_frequency_summaries(departures: list[BusDepartureItem]) -> list[RouteFrequencySummary]:
    grouped: dict[str, list[BusDepartureItem]] = defaultdict(list)
    for departure in departures:
        grouped[departure.route_number].append(departure)

    summaries: list[RouteFrequencySummary] = []
    for route_number, route_departures in grouped.items():
        times = [
            item.expected_at or item.scheduled_at
            for item in route_departures
            if (item.expected_at or item.scheduled_at) is not None
        ]
        times = sorted(time for time in times if time is not None)
        spacing = None
        if len(times) >= 2:
            diffs = [
                int((later - earlier).total_seconds() // 60)
                for earlier, later in zip(times[:-1], times[1:])
            ]
            spacing = int(median(diffs))
        next_due = route_departures[0].due_minutes if route_departures else None
        summaries.append(
            RouteFrequencySummary(
                route_number=route_number,
                departures_count=len(route_departures),
                median_spacing_minutes=spacing,
                band=_band_for_spacing(spacing),
                next_due_minutes=next_due,
            )
        )
    return sorted(
        summaries,
        key=lambda summary: (summary.next_due_minutes is None, summary.next_due_minutes or 999, summary.route_number),
    )


def derive_leave_by_recommendation(
    departures: list[BusDepartureItem],
    now: datetime,
    walking_buffer_minutes: int,
) -> LeaveByRecommendation:
    if not departures:
        return LeaveByRecommendation(
            walking_buffer_minutes=walking_buffer_minutes,
            status=LeaveByStatus.UNAVAILABLE,
        )
    target = departures[0].expected_at or departures[0].scheduled_at
    if target is None:
        return LeaveByRecommendation(
            walking_buffer_minutes=walking_buffer_minutes,
            status=LeaveByStatus.UNAVAILABLE,
        )
    leave_by = target - timedelta(minutes=walking_buffer_minutes)
    if target <= now:
        status = LeaveByStatus.MISSED
    elif leave_by <= now:
        status = LeaveByStatus.LEAVE_NOW
    elif leave_by <= now + timedelta(minutes=2):
        status = LeaveByStatus.LEAVE_SOON
    else:
        status = LeaveByStatus.BUFFERED
    return LeaveByRecommendation(
        walking_buffer_minutes=walking_buffer_minutes,
        leave_by_at=leave_by,
        target_departure_at=target,
        status=status,
    )


def derive_irregularity_summary(departures: list[BusDepartureItem]) -> list[str]:
    notes: list[str] = []
    for departure in departures:
        if departure.marker:
            notes.append(f"R{departure.route_number}: {departure.marker}")
        elif departure.delay_minutes and departure.delay_minutes > 2:
            notes.append(f"R{departure.route_number}: Delay +{departure.delay_minutes}m")
    return notes[:3]


def build_stop_insight(
    stop: SavedStop,
    departures: list[BusDepartureItem],
    now: datetime,
    walking_buffer_minutes: int,
) -> StopInsightSnapshot:
    departures = sorted(
        departures,
        key=lambda item: item.expected_at or item.scheduled_at or now + timedelta(days=1),
    )
    return StopInsightSnapshot(
        stop_id=stop.stop_id,
        stop_title=stop.title,
        departures=departures,
        hero=derive_next_bus_hero(departures, stop),
        density_window=derive_service_density(departures, now),
        frequency_summaries=derive_route_frequency_summaries(departures),
        irregularity_summary=derive_irregularity_summary(departures),
        leave_by=derive_leave_by_recommendation(departures, now, walking_buffer_minutes),
    )


def build_multi_stop_snapshot(
    stops: list[SavedStop],
    departures_by_stop: dict[str, list[BusDepartureItem]],
    now: datetime,
    walking_buffer_minutes: int,
) -> MultiStopSnapshot:
    return MultiStopSnapshot(
        stops=[
            build_stop_insight(
                stop,
                departures_by_stop.get(stop.stop_id, []),
                now,
                walking_buffer_minutes,
            )
            for stop in stops
        ]
    )

