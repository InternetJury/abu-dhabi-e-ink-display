from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "pi" / "display-current.py"
spec = importlib.util.spec_from_file_location("display_current", MODULE_PATH)
assert spec is not None
display_current = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = display_current
spec.loader.exec_module(display_current)


class FakeDriver:
    def __init__(self) -> None:
        self.is_open = False
        self.open_calls = 0
        self.clear_calls = 0
        self.display_calls: list[bool] = []
        self.close_calls = 0

    def open(self) -> None:
        self.is_open = True
        self.open_calls += 1

    def clear(self) -> None:
        self.clear_calls += 1

    def display(self, _image: Image.Image, full_refresh: bool) -> None:
        self.display_calls.append(full_refresh)

    def close(self) -> None:
        self.is_open = False
        self.close_calls += 1


def make_args(**overrides):
    values = {
        "max_frame_age_seconds": 50.0,
        "require_current_minute": False,
        "latest_display_start_second": 45.0,
        "expected_width": 1360,
        "expected_height": 480,
        "startup_delay_seconds": 0.0,
        "clear_on_start": True,
        "full_refresh_seconds": 300,
        "disable_partial": True,
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


def write_frame(path: Path) -> None:
    Image.new("1", (1360, 480), 255).save(path)


def test_stale_frame_does_not_open_or_power_display(tmp_path: Path):
    frame = tmp_path / "current.png"
    write_frame(frame)
    os.utime(frame, (100.0, 100.0))
    driver = FakeDriver()
    state = display_current.DisplayState(startup_full_refreshes_remaining=1)

    displayed = display_current.process_frame_once(
        frame,
        driver,
        make_args(),
        state,
        wall_time=lambda: 1000.0,
        monotonic=lambda: 20.0,
        sleeper=lambda _seconds: None,
    )

    assert displayed is False
    assert driver.open_calls == 0
    assert driver.clear_calls == 0
    assert driver.display_calls == []


def test_previous_minute_frame_never_opens_or_powers_display(tmp_path: Path):
    frame = tmp_path / "current.png"
    write_frame(frame)
    os.utime(frame, (120.0, 120.0))
    driver = FakeDriver()
    state = display_current.DisplayState(startup_full_refreshes_remaining=1)

    displayed = display_current.process_frame_once(
        frame,
        driver,
        make_args(require_current_minute=True),
        state,
        wall_time=lambda: 181.0,
        monotonic=lambda: 20.0,
        sleeper=lambda _seconds: None,
    )

    assert displayed is False
    assert driver.open_calls == 0
    assert driver.display_calls == []


def test_late_current_minute_frame_is_rejected_before_refresh(tmp_path: Path):
    frame = tmp_path / "current.png"
    write_frame(frame)
    os.utime(frame, (185.0, 185.0))
    driver = FakeDriver()
    state = display_current.DisplayState(startup_full_refreshes_remaining=1)

    displayed = display_current.process_frame_once(
        frame,
        driver,
        make_args(require_current_minute=True, latest_display_start_second=45.0),
        state,
        wall_time=lambda: 226.0,
        monotonic=lambda: 20.0,
        sleeper=lambda _seconds: None,
    )

    assert displayed is False
    assert driver.open_calls == 0
    assert driver.display_calls == []


def test_first_fresh_frame_opens_clears_and_forces_full_refresh(tmp_path: Path):
    frame = tmp_path / "current.png"
    write_frame(frame)
    os.utime(frame, (995.0, 995.0))
    driver = FakeDriver()
    state = display_current.DisplayState(startup_full_refreshes_remaining=1)

    displayed = display_current.process_frame_once(
        frame,
        driver,
        make_args(),
        state,
        wall_time=lambda: 1000.0,
        monotonic=lambda: 20.0,
        sleeper=lambda _seconds: None,
    )

    assert displayed is True
    assert driver.open_calls == 1
    assert driver.clear_calls == 1
    assert driver.display_calls == [True]
    assert state.startup_full_refreshes_remaining == 0


def test_first_full_display_initializes_panel_exactly_once(monkeypatch):
    calls: list[str] = []

    class FakeEPD:
        def init(self):
            calls.append("init")

        def getbuffer(self, image):
            calls.append("getbuffer")
            return image

        def display(self, _payload):
            calls.append("display")

        def sleep(self):
            calls.append("sleep")

    fake_module = types.SimpleNamespace(EPD=FakeEPD)
    monkeypatch.setattr(display_current.importlib, "import_module", lambda _name: fake_module)

    driver = display_current.EInkDriver("fake_epd", None, False, True)
    driver.open()
    assert calls == []

    driver.display(Image.new("1", (1360, 480), 255), full_refresh=True)

    assert calls.count("init") == 1
    assert calls[-1] == "display"


def test_hardware_is_closed_after_idle_timeout():
    driver = FakeDriver()
    driver.open()
    state = display_current.DisplayState(
        startup_full_refreshes_remaining=0,
        last_hardware_activity=100.0,
    )

    closed = display_current.close_idle_driver(
        driver,
        state,
        hardware_idle_seconds=120.0,
        monotonic=lambda: 221.0,
    )

    assert closed is True
    assert driver.close_calls == 1


def test_driver_close_sleeps_panel_before_releasing_hardware(monkeypatch):
    calls: list[str] = []

    class FakeEPD:
        def init(self):
            calls.append("init")

        def getbuffer(self, image):
            return image

        def display(self, _payload):
            calls.append("display")

        def sleep(self):
            calls.append("sleep")

    fake_module = types.SimpleNamespace(EPD=FakeEPD)
    monkeypatch.setattr(display_current.importlib, "import_module", lambda _name: fake_module)

    driver = display_current.EInkDriver("fake_epd", None, False, True)
    driver.open()
    driver.display(Image.new("1", (1360, 480), 255), full_refresh=True)
    driver.close()

    assert calls == ["init", "display", "sleep"]
    assert driver.is_open is False


def test_failed_driver_init_releases_panel_power(monkeypatch):
    calls: list[str] = []

    class FakeEPD:
        def init(self):
            calls.append("init")
            raise RuntimeError("controller init failed")

        def getbuffer(self, image):
            return image

        def display(self, _payload):
            calls.append("display")

        def sleep(self):
            calls.append("sleep")

    fake_module = types.SimpleNamespace(EPD=FakeEPD)
    monkeypatch.setattr(display_current.importlib, "import_module", lambda _name: fake_module)

    driver = display_current.EInkDriver("fake_epd", None, False, True)
    driver.open()
    try:
        driver.display(Image.new("1", (1360, 480), 255), full_refresh=True)
    except RuntimeError as exc:
        assert "controller init failed" in str(exc)
    else:
        raise AssertionError("failed vendor init unexpectedly succeeded")

    assert calls == ["init", "sleep"]
    assert driver.is_open is False


def test_process_lock_rejects_second_writer(tmp_path: Path):
    first = display_current.ProcessLock(tmp_path / "display.lock")
    second = display_current.ProcessLock(tmp_path / "display.lock")

    first.acquire()
    try:
        try:
            second.acquire()
        except RuntimeError as exc:
            assert "already owns" in str(exc)
        else:
            raise AssertionError("second display writer unexpectedly acquired the lock")
    finally:
        first.release()
