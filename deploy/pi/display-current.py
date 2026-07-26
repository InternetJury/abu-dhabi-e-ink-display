#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import time
from pathlib import Path
from typing import Callable

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EInkDriver:
    def __init__(
        self,
        module_name: str | None,
        driver_lib: str | None,
        dry_run: bool,
        disable_partial: bool,
    ) -> None:
        self.module_name = module_name
        self.driver_lib = driver_lib
        self.dry_run = dry_run or not module_name
        self.disable_partial = disable_partial
        self.epd = None
        self.partial_ready = False
        self._is_open = False
        self._initialized_mode: str | None = None
        self._hardware_touched = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        if self._is_open:
            return
        if self.dry_run:
            logging.info("Display client running in dry-run/checksum mode.")
            self._is_open = True
            return

        if self.driver_lib:
            sys.path.insert(0, self.driver_lib)

        module = importlib.import_module(self.module_name or "")
        epd_class = getattr(module, "EPD", None)
        if epd_class is None:
            raise RuntimeError(f"{self.module_name} does not expose an EPD class.")

        self.epd = epd_class()
        self._is_open = True
        logging.info("Loaded e-ink driver module %s", self.module_name)

    def _initialize(self, partial: bool = False) -> None:
        if self.epd is None:
            raise RuntimeError("Display driver has not been opened.")

        requested_mode = "partial" if partial else "full"
        if self._initialized_mode == requested_mode:
            return

        init = getattr(self.epd, "init_Part" if partial else "init", None)
        if not callable(init) and partial:
            init = getattr(self.epd, "init", None)
        if not callable(init):
            self._initialized_mode = requested_mode
            return

        self._hardware_touched = True
        try:
            init()
        except Exception:
            # Vendor init may already have enabled the panel power rail.
            self.close()
            raise

        self._initialized_mode = requested_mode
        self.partial_ready = partial

    def close(self) -> None:
        if not self._is_open and self.epd is None:
            return

        try:
            if not self.dry_run and self.epd is not None and self._hardware_touched:
                sleep = getattr(self.epd, "sleep", None)
                if callable(sleep):
                    sleep()
                else:
                    logging.warning("Display driver has no sleep method; releasing it without panel sleep.")
        except Exception:
            logging.exception("Display sleep failed while releasing the hardware.")
        finally:
            self.epd = None
            self.partial_ready = False
            self._initialized_mode = None
            self._hardware_touched = False
            self._is_open = False

    def clear(self) -> None:
        if self.dry_run:
            logging.info("Dry-run display clear accepted.")
            return

        if self.epd is None:
            raise RuntimeError("Display driver has not been opened.")

        self._initialize(partial=False)

        clear = getattr(self.epd, "Clear", None)
        if not callable(clear):
            logging.warning("Display driver has no Clear method; startup clear skipped.")
            return

        clear()
        self.partial_ready = False

    def display(self, image: Image.Image, full_refresh: bool) -> None:
        if self.dry_run:
            logging.info("Dry-run display update accepted; full_refresh=%s", full_refresh)
            return

        if self.epd is None:
            raise RuntimeError("Display driver has not been opened.")

        frame = image.convert("1")
        getbuffer = getattr(self.epd, "getbuffer", None)
        payload = getbuffer(frame) if callable(getbuffer) else frame

        if not full_refresh and not self.disable_partial and hasattr(self.epd, "display_Partial"):
            self._initialize(partial=True)
            self._display_partial(payload)
        elif hasattr(self.epd, "display"):
            self._initialize(partial=False)
            self.epd.display(payload)
        else:
            raise RuntimeError("Display driver has no display/display_Partial method.")

    def _display_partial(self, payload: object) -> None:
        partial = getattr(self.epd, "display_Partial")
        parameters = inspect.signature(partial).parameters
        if len(parameters) >= 5:
            width = int(getattr(self.epd, "width", 1360))
            height = int(getattr(self.epd, "height", 480))
            partial(payload, 0, 0, width, height)
        else:
            partial(payload)


@dataclass
class DisplayState:
    last_digest: str = ""
    last_stale_digest: str = ""
    last_full_refresh: float = 0.0
    startup_full_refreshes_remaining: int = 1
    last_hardware_activity: float = 0.0
    startup_prepared: bool = False


class ProcessLock:
    """Cross-platform non-blocking lock that permits one display writer."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> None:
        if self._handle is not None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if self.path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeError(f"Another process already owns the display lock {self.path}") from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return

        handle = self._handle
        self._handle = None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def process_frame_once(
    frame_path: Path,
    driver: EInkDriver,
    args,
    state: DisplayState,
    *,
    wall_time: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Validate a frame before opening or powering the display hardware."""
    if not frame_path.exists():
        logging.info("Waiting for %s", frame_path)
        return False

    digest = sha256_file(frame_path)
    if digest == state.last_digest:
        return False

    frame_stat = frame_path.stat()
    now_wall = wall_time()
    frame_age = now_wall - frame_stat.st_mtime
    if args.max_frame_age_seconds >= 0 and frame_age > args.max_frame_age_seconds:
        if digest != state.last_stale_digest:
            logging.warning(
                "Skipping stale frame %s; age %.1fs exceeds %.1fs",
                frame_path,
                frame_age,
                args.max_frame_age_seconds,
            )
            state.last_stale_digest = digest
        return False

    if args.require_current_minute:
        frame_minute = int(frame_stat.st_mtime // 60)
        current_minute = int(now_wall // 60)
        second_in_minute = now_wall % 60
        timing_error = None
        if frame_minute != current_minute:
            timing_error = "its render minute is not the current minute"
        elif second_in_minute > args.latest_display_start_second:
            timing_error = (
                f"second {second_in_minute:.1f} exceeds the safe display-start cutoff "
                f"of {args.latest_display_start_second:.1f}"
            )

        if timing_error is not None:
            if digest != state.last_stale_digest:
                logging.warning("Skipping off-slot frame %s; %s", frame_path, timing_error)
                state.last_stale_digest = digest
            return False

    # Decode and validate dimensions before importing a vendor driver or
    # energising the panel power rails.
    image = load_frame(frame_path, args.expected_width, args.expected_height)

    opened_here = False
    try:
        if not driver.is_open:
            if args.startup_delay_seconds > 0:
                logging.info("Waiting %.1fs before display driver init.", args.startup_delay_seconds)
                sleeper(args.startup_delay_seconds)
            driver.open()
            opened_here = True
            if args.clear_on_start and not state.startup_prepared:
                logging.info("Clearing display before accepting the first fresh frame.")
                driver.clear()
            state.startup_prepared = True

        now = monotonic()
        force_startup_full = state.startup_full_refreshes_remaining > 0
        full_refresh = force_startup_full or (now - state.last_full_refresh) >= args.full_refresh_seconds
        hardware_full_refresh = full_refresh or args.disable_partial
        driver.display(image, full_refresh=hardware_full_refresh)

        if hardware_full_refresh:
            state.last_full_refresh = now
        if force_startup_full:
            state.startup_full_refreshes_remaining -= 1
        state.last_hardware_activity = now
        state.last_digest = digest
        state.last_stale_digest = ""
        logging.info(
            "Displayed %s sha256=%s full_refresh=%s startup_full_remaining=%s",
            frame_path,
            digest[:12],
            hardware_full_refresh,
            state.startup_full_refreshes_remaining,
        )
        return True
    except Exception:
        # Never leave a failed init/write holding panel power indefinitely.
        driver.close()
        state.startup_prepared = False
        state.startup_full_refreshes_remaining = max(1, state.startup_full_refreshes_remaining)
        raise


def close_idle_driver(
    driver: EInkDriver,
    state: DisplayState,
    hardware_idle_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    if not driver.is_open or hardware_idle_seconds < 0 or state.last_hardware_activity <= 0:
        return False
    if monotonic() - state.last_hardware_activity < hardware_idle_seconds:
        return False

    logging.info("Display hardware idle for %.1fs; putting panel to sleep.", hardware_idle_seconds)
    driver.close()
    state.startup_prepared = False
    state.startup_full_refreshes_remaining = max(1, state.startup_full_refreshes_remaining)
    return True


def configure_logging(log_file: Path | None, max_bytes: int, backup_count: int) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def load_frame(path: Path, width: int, height: int) -> Image.Image:
    image = Image.open(path)
    if image.size != (width, height):
        raise ValueError(f"Expected {width}x{height}, got {image.size[0]}x{image.size[1]}")
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="Display the current Abu Dhabi e-ink PNG when it changes.")
    parser.add_argument("--image", default="/var/lib/abu-dhabi-eink/current.png")
    parser.add_argument("--expected-width", type=int, default=1360)
    parser.add_argument("--expected-height", type=int, default=480)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--full-refresh-seconds", type=int, default=300)
    parser.add_argument("--max-frame-age-seconds", type=float, default=50.0)
    parser.add_argument(
        "--require-current-minute",
        action="store_true",
        help="Accept a frame only during the same wall-clock minute recorded in its mtime.",
    )
    parser.add_argument(
        "--latest-display-start-second",
        type=float,
        default=45.0,
        help="Reject a frame after this second in its render minute so refresh cannot finish late.",
    )
    parser.add_argument(
        "--hardware-idle-seconds",
        type=float,
        default=120.0,
        help="Sleep and release the panel after this many seconds without a successful frame.",
    )
    parser.add_argument("--lock-file", default="/run/abu-dhabi-eink/display.lock")
    parser.add_argument(
        "--startup-delay-seconds",
        type=float,
        default=0.0,
        help="Wait before opening the hardware driver so the HAT and panel power rails settle after boot.",
    )
    parser.add_argument(
        "--clear-on-start",
        action="store_true",
        help="Clear both e-paper controller halves once when the service starts.",
    )
    parser.add_argument(
        "--startup-full-refresh-count",
        type=int,
        default=1,
        help="Force this many valid changed frames through the full-refresh path after service start.",
    )
    parser.add_argument("--driver-module", default=None, help="Vendor Python module exposing EPD, for example waveshare_epd.epd13in3.")
    parser.add_argument("--driver-lib", default=None, help="Directory to prepend to PYTHONPATH before importing the driver module.")
    parser.add_argument(
        "--disable-partial",
        action="store_true",
        help="Always use the driver's full-frame display path. Recommended for split-controller panels with unreliable partial refresh.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-file", default="/var/log/abu-dhabi-eink/display-current.log")
    parser.add_argument("--log-max-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--log-backups", type=int, default=3)
    args = parser.parse_args()

    configure_logging(Path(args.log_file) if args.log_file else None, args.log_max_bytes, args.log_backups)

    frame_path = Path(args.image)
    driver = EInkDriver(args.driver_module, args.driver_lib, args.dry_run, args.disable_partial)
    state = DisplayState(startup_full_refreshes_remaining=max(0, args.startup_full_refresh_count))
    process_lock = ProcessLock(args.lock_file)
    stop_requested = False

    def request_stop(signum, _frame) -> None:
        nonlocal stop_requested
        logging.info("Received signal %s; stopping after safe display shutdown.", signum)
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    process_lock.acquire()
    try:
        while not stop_requested:
            try:
                process_frame_once(frame_path, driver, args, state)
                close_idle_driver(driver, state, args.hardware_idle_seconds)
            except Exception as exc:
                logging.exception("Display update failed: %s", exc)

            if args.once:
                break
            time.sleep(args.poll_seconds)
    finally:
        driver.close()
        process_lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
