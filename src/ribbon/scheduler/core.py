from __future__ import annotations

import hashlib
import json
from datetime import datetime, time

from ribbon.models import ModeName, RefreshHint, RibbonSnapshot
from ribbon.settings import SETTINGS


WEEKEND_ROTATION = [
    ModeName.WEEKEND_MULTI_STOP,
    ModeName.AMBIENT_INFO,
]


def _weekday_window(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    start = time(SETTINGS.weekday_commute_start_hour, SETTINGS.weekday_commute_start_minute)
    end = time(SETTINGS.weekday_commute_end_hour, SETTINGS.weekday_commute_end_minute)
    return start <= now.timetz().replace(tzinfo=None) <= end


def _rotation_index(now: datetime, modes: list[ModeName]) -> int:
    minutes_since_midnight = now.hour * 60 + now.minute
    return (minutes_since_midnight // SETTINGS.rotation_minutes) % len(modes)


def _minute_rotation_index(now: datetime, modes: list[ModeName]) -> int:
    minutes_since_midnight = now.hour * 60 + now.minute
    return minutes_since_midnight % len(modes)


def select_mode(now: datetime) -> ModeName:
    if _weekday_window(now):
        return ModeName.WEEKDAY_COMMUTE_NOW
    if now.weekday() >= 5:
        return WEEKEND_ROTATION[_minute_rotation_index(now, WEEKEND_ROTATION)]
    return ModeName.AMBIENT_INFO


def snapshot_signature(snapshot: RibbonSnapshot) -> str:
    payload = snapshot.model_dump(mode="json", exclude={"generated_at", "refresh_hint"})
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def compute_refresh_hint(
    now: datetime,
    current_mode: ModeName,
    previous_mode: ModeName | None = None,
    previous_signature: str | None = None,
    current_signature: str | None = None,
) -> RefreshHint:
    if previous_mode is None:
        return RefreshHint.FULL
    if current_mode != previous_mode:
        return RefreshHint.FULL
    if current_signature and previous_signature and current_signature != previous_signature:
        return RefreshHint.FULL
    if now.minute % SETTINGS.full_refresh_minutes == 0 and now.second < SETTINGS.render_interval_seconds:
        return RefreshHint.FULL
    return RefreshHint.INCREMENTAL
