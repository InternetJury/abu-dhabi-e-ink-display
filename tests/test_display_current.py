from __future__ import annotations

import importlib.util
import errno
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


def test_load_frame_closes_png_source_and_returns_detached_copy(monkeypatch, tmp_path: Path):
    frame_path = tmp_path / "current.png"
    frame_path.touch()
    detached = Image.new("1", (1360, 480), 255)

    class TrackingSource:
        size = (1360, 480)
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            self.closed = True

        def load(self):
            return None

        def copy(self):
            return detached

    source = TrackingSource()
    monkeypatch.setattr(display_current.Image, "open", lambda _path: source)

    loaded = display_current.load_frame(frame_path, 1360, 480)

    assert loaded is detached
    assert source.closed is True


def test_load_frame_closes_png_source_when_dimensions_are_invalid(monkeypatch, tmp_path: Path):
    frame_path = tmp_path / "current.png"
    frame_path.touch()

    class TrackingSource:
        size = (100, 100)
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            self.closed = True

    source = TrackingSource()
    monkeypatch.setattr(display_current.Image, "open", lambda _path: source)

    try:
        display_current.load_frame(frame_path, 1360, 480)
    except ValueError as exc:
        assert "Expected 1360x480" in str(exc)
    else:
        raise AssertionError("invalid frame dimensions unexpectedly passed")

    assert source.closed is True


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


def test_processed_frame_is_closed_after_display(monkeypatch, tmp_path: Path):
    frame = tmp_path / "current.png"
    write_frame(frame)
    os.utime(frame, (995.0, 995.0))
    driver = FakeDriver()
    state = display_current.DisplayState(startup_full_refreshes_remaining=1)

    class TrackingFrame:
        close_calls = 0

        def close(self):
            self.close_calls += 1

    loaded = TrackingFrame()
    monkeypatch.setattr(display_current, "load_frame", lambda *_args: loaded)

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
    assert loaded.close_calls == 1


def test_display_loop_exits_for_systemd_restart_on_file_descriptor_exhaustion(monkeypatch, tmp_path: Path):
    driver = FakeDriver()
    state = display_current.DisplayState()

    class FakeLock:
        acquired = False
        released = False

        def acquire(self):
            self.acquired = True

        def release(self):
            self.released = True

    process_lock = FakeLock()
    attempts = 0

    def fail_with_emfile(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError(errno.EMFILE, "Too many open files")

    monkeypatch.setattr(display_current, "process_frame_once", fail_with_emfile)
    monkeypatch.setattr(display_current.time, "sleep", lambda _seconds: None)
    args = make_args(once=False, poll_seconds=1.0, hardware_idle_seconds=90.0, max_consecutive_errors=5)

    exit_code = display_current.run_display_loop(
        tmp_path / "current.png",
        driver,
        args,
        state,
        process_lock,
    )

    assert exit_code == 1
    assert attempts == 1
    assert process_lock.acquired is True
    assert process_lock.released is True
    assert driver.close_calls == 1


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


def test_monochrome_conversion_uses_deterministic_threshold_without_dithering():
    image = Image.new("L", (4, 1))
    image.putdata([0, 199, 200, 255])

    converted = display_current.to_monochrome(image, threshold=200)

    assert [converted.getpixel((x, 0)) for x in range(4)] == [0, 0, 255, 255]


def test_partial_mode_reinitializes_before_every_frame(monkeypatch):
    calls: list[str] = []

    class FakeEPD:
        width = 1360
        height = 480

        def init_Part(self):
            calls.append("init_part")

        def getbuffer(self, image):
            return image

        def display_Partial(self, _payload, _x0, _y0, _x1, _y1):
            calls.append("partial")

    fake_module = types.SimpleNamespace(EPD=FakeEPD)
    monkeypatch.setattr(display_current.importlib, "import_module", lambda _name: fake_module)

    driver = display_current.EInkDriver("fake_epd", None, False, False)
    driver.open()
    frame = Image.new("1", (1360, 480), 255)
    driver.display(frame, full_refresh=False)
    driver.display(frame, full_refresh=False)

    assert calls == ["init_part", "partial", "init_part", "partial"]


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
