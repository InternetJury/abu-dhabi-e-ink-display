from datetime import datetime
from zoneinfo import ZoneInfo

from ribbon.models import ModeName, RefreshHint
from ribbon.scheduler import compute_refresh_hint, select_mode
from ribbon.settings import SETTINGS


TZ = ZoneInfo("Asia/Dubai")


def test_select_mode_uses_commute_window_on_weekday():
    now = datetime(2026, 4, 6, 6, 15, tzinfo=TZ)  # Monday
    assert select_mode(now) == ModeName.WEEKDAY_COMMUTE_NOW


def test_select_mode_keeps_commute_window_until_eight_am():
    now = datetime(2026, 4, 6, 7, 45, tzinfo=TZ)
    assert select_mode(now) == ModeName.WEEKDAY_COMMUTE_NOW


def test_select_mode_uses_ambient_mode_weekday_outside_commute_window():
    now = datetime(2026, 4, 6, 9, 0, tzinfo=TZ)
    assert select_mode(now) == ModeName.AMBIENT_INFO


def test_select_mode_rotates_weekend_multi_stop():
    now = datetime(2026, 4, 11, 10, 0, tzinfo=TZ)  # Saturday
    assert select_mode(now) == ModeName.WEEKEND_MULTI_STOP


def test_refresh_hint_promotes_full_refresh_on_mode_change():
    now = datetime(2026, 4, 6, 9, 0, tzinfo=TZ)
    assert compute_refresh_hint(now, ModeName.AMBIENT_INFO, previous_mode=ModeName.WEEKDAY_COMMUTE_NOW) == RefreshHint.FULL


def test_refresh_hint_uses_sixty_second_render_cadence():
    assert SETTINGS.render_interval_seconds == 60
