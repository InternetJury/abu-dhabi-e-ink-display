from __future__ import annotations

from datetime import timedelta

from ribbon.models import BusDepartureItem, RibbonSnapshot, StopInsightSnapshot


def snapshot_with_uniform_delay(snapshot: RibbonSnapshot, delay_minutes: int = 4) -> RibbonSnapshot:
    delta = timedelta(minutes=delay_minutes)
    marker = f"Delay +{delay_minutes}m"

    def delay_stop(stop: StopInsightSnapshot) -> StopInsightSnapshot:
        departures = []
        for departure in stop.departures:
            expected_base = departure.scheduled_at or departure.expected_at
            expected_at = expected_base + delta if expected_base else departure.expected_at
            due_minutes = departure.due_minutes + delay_minutes if departure.due_minutes is not None else None
            departures.append(
                departure.model_copy(
                    update={
                        "expected_at": expected_at,
                        "due_minutes": due_minutes,
                        "delay_minutes": delay_minutes,
                        "marker": marker,
                    }
                )
            )

        hero = stop.hero
        if hero and departures:
            hero_departure = departures[0]
            hero = hero.model_copy(
                update={
                    "due_label": _format_due_label(hero_departure.due_minutes),
                    "scheduled_label": _format_scheduled_label(hero_departure),
                    "irregularity_flag": marker,
                }
            )

        irregularity_summary = [f"R{departure.route_number}: {marker}" for departure in departures[:3]]
        return stop.model_copy(
            update={
                "departures": departures,
                "hero": hero,
                "irregularity_summary": irregularity_summary,
            }
        )

    primary_stop = delay_stop(snapshot.primary_stop) if snapshot.primary_stop else None
    multi_stop = (
        snapshot.multi_stop.model_copy(update={"stops": [delay_stop(stop) for stop in snapshot.multi_stop.stops]})
        if snapshot.multi_stop
        else None
    )
    return snapshot.model_copy(update={"primary_stop": primary_stop, "multi_stop": multi_stop})


def _format_due_label(due_minutes: int | None) -> str:
    if due_minutes is None:
        return "-- min"
    if due_minutes <= 0:
        return "due"
    return f"{due_minutes:02d} min"


def _format_scheduled_label(departure: BusDepartureItem) -> str | None:
    target = departure.scheduled_at
    return target.strftime("%H:%M") if target else None
