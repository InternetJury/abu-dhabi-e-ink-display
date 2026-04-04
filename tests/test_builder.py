from datetime import datetime
from zoneinfo import ZoneInfo

from ribbon.derive.builder import build_live_snapshot
from ribbon.fixtures import load_fixture_snapshot
from ribbon.models import ModeName, RefreshHint
from ribbon.providers import FixtureBusProvider, FixtureHeadlineProvider, FixtureWeatherProvider


def test_fixture_backed_builder_produces_weekend_multi_stop_snapshot():
    now = datetime(2026, 4, 11, 10, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    snapshot = build_live_snapshot(
        mode=ModeName.WEEKEND_MULTI_STOP,
        now=now,
        refresh_hint=RefreshHint.FULL,
        bus_provider=FixtureBusProvider("weekend_multi_stop"),
        weather_provider=FixtureWeatherProvider("weekend_multi_stop"),
        headline_provider=FixtureHeadlineProvider("weekend_multi_stop"),
    )
    assert snapshot.multi_stop is not None
    assert len(snapshot.multi_stop.stops) == 4
    assert snapshot.city_summary is not None


def test_fixture_loader_roundtrips_snapshot_mode():
    snapshot = load_fixture_snapshot("ambient_info")
    assert snapshot.mode == ModeName.AMBIENT_INFO
    assert len(snapshot.headlines) == 6
