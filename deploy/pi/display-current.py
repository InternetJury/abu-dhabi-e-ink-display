#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import logging
from logging.handlers import RotatingFileHandler
import sys
import time
from pathlib import Path

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EInkDriver:
    def __init__(self, module_name: str | None, driver_lib: str | None, dry_run: bool) -> None:
        self.module_name = module_name
        self.driver_lib = driver_lib
        self.dry_run = dry_run or not module_name
        self.epd = None
        self.partial_ready = False

    def open(self) -> None:
        if self.dry_run:
            logging.info("Display client running in dry-run/checksum mode.")
            return

        if self.driver_lib:
            sys.path.insert(0, self.driver_lib)

        module = importlib.import_module(self.module_name or "")
        epd_class = getattr(module, "EPD", None)
        if epd_class is None:
            raise RuntimeError(f"{self.module_name} does not expose an EPD class.")

        self.epd = epd_class()
        if hasattr(self.epd, "init"):
            self.epd.init()
        logging.info("Loaded e-ink driver module %s", self.module_name)

    def display(self, image: Image.Image, full_refresh: bool) -> None:
        if self.dry_run:
            logging.info("Dry-run display update accepted; full_refresh=%s", full_refresh)
            return

        if self.epd is None:
            raise RuntimeError("Display driver has not been opened.")

        frame = image.convert("1")
        getbuffer = getattr(self.epd, "getbuffer", None)
        payload = getbuffer(frame) if callable(getbuffer) else frame

        if full_refresh and hasattr(self.epd, "init"):
            self.epd.init()
            self.partial_ready = False

        if not full_refresh and hasattr(self.epd, "display_Partial"):
            if not self.partial_ready and hasattr(self.epd, "init_Part"):
                self.epd.init_Part()
                self.partial_ready = True
            self._display_partial(payload)
        elif hasattr(self.epd, "display"):
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
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--full-refresh-seconds", type=int, default=300)
    parser.add_argument("--driver-module", default=None, help="Vendor Python module exposing EPD, for example waveshare_epd.epd13in3.")
    parser.add_argument("--driver-lib", default=None, help="Directory to prepend to PYTHONPATH before importing the driver module.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-file", default="/var/log/abu-dhabi-eink/display-current.log")
    parser.add_argument("--log-max-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--log-backups", type=int, default=3)
    args = parser.parse_args()

    configure_logging(Path(args.log_file) if args.log_file else None, args.log_max_bytes, args.log_backups)

    frame_path = Path(args.image)
    driver = EInkDriver(args.driver_module, args.driver_lib, args.dry_run)
    driver.open()

    last_digest = ""
    last_full_refresh = 0.0

    while True:
        try:
            if not frame_path.exists():
                logging.info("Waiting for %s", frame_path)
            else:
                digest = sha256_file(frame_path)
                if digest != last_digest:
                    image = load_frame(frame_path, args.expected_width, args.expected_height)
                    now = time.monotonic()
                    full_refresh = (now - last_full_refresh) >= args.full_refresh_seconds
                    driver.display(image, full_refresh=full_refresh)
                    if full_refresh:
                        last_full_refresh = now
                    last_digest = digest
                    logging.info("Displayed %s sha256=%s", frame_path, digest[:12])
        except Exception as exc:
            logging.exception("Display update failed: %s", exc)

        if args.once:
            break
        time.sleep(args.poll_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
