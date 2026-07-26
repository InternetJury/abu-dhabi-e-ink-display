#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import logging
import os
from pathlib import Path
import subprocess
import sys

try:
    import fcntl
except ImportError:  # Windows can still validate previews; hardware apply is Linux-only.
    fcntl = None

from PIL import Image


WIDTH = 1360
HEIGHT = 480


@dataclass(frozen=True)
class TransferEvent:
    controller: str
    byte_count: int
    sha256: str


class TransferTrace:
    """Record bulk RAM writes without changing the vendor transfer path."""

    def __init__(self) -> None:
        self.events: list[TransferEvent] = []

    def install(self, epd) -> None:
        target = getattr(epd, "_epd", epd)
        for controller in ("M", "S"):
            name = f"send_data2_{controller}"
            original = getattr(target, name)

            def traced(data, *, _controller=controller, _original=original):
                payload = bytes(data)
                event = TransferEvent(
                    controller=_controller,
                    byte_count=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
                self.events.append(event)
                return _original(data)

            setattr(target, name, traced)

    def summary(self, controller: str) -> dict[str, int]:
        events = [event for event in self.events if event.controller == controller]
        return {
            "count": len(events),
            "total_bytes": sum(event.byte_count for event in events),
            "max_bytes": max((event.byte_count for event in events), default=0),
        }


def build_pattern(mode: str) -> Image.Image:
    if mode == "full-white":
        return Image.new("1", (WIDTH, HEIGHT), 255)
    if mode == "full-black":
        return Image.new("1", (WIDTH, HEIGHT), 0)

    image = Image.new("1", (WIDTH, HEIGHT), 255)
    if mode == "left-black":
        image.paste(0, (0, 0, WIDTH // 2, HEIGHT))
        return image
    if mode == "right-black":
        image.paste(0, (WIDTH // 2, 0, WIDTH, HEIGHT))
        return image
    raise ValueError(f"Unsupported diagnostic mode: {mode}")


def load_live_frame(path: Path) -> Image.Image:
    image = Image.open(path)
    if image.size != (WIDTH, HEIGHT):
        raise ValueError(f"Expected {WIDTH}x{HEIGHT}, got {image.size[0]}x{image.size[1]}")
    return image.convert("1")


class ExclusiveDisplayLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        if fcntl is None:
            raise RuntimeError("Display locking requires Linux fcntl support")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError(f"Another process already owns the display lock {self.path}") from exc
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def assert_service_inactive(service_name: str) -> None:
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service_name],
        check=False,
    )
    if result.returncode == 0:
        raise RuntimeError(f"Refusing hardware access while {service_name} is active")


def apply_pattern(args, image: Image.Image) -> None:
    assert_service_inactive(args.service_name)
    os.environ["WAVESHARE_10IN85_VENDOR_LIB"] = args.vendor_lib
    os.environ["WAVESHARE_10IN85_SPI_HZ"] = str(args.spi_hz)
    sys.path.insert(0, args.driver_lib)

    with ExclusiveDisplayLock(Path(args.lock_file)):
        module = importlib.import_module(args.driver_module)
        epd = module.EPD()
        trace = TransferTrace()
        trace.install(epd)
        try:
            epd.init()
            epd.display(epd.getbuffer(image))
            master = trace.summary("M")
            slave = trace.summary("S")
            logging.info(
                "Applied one full-frame %s diagnostic; "
                "M writes=%d total=%d max=%d; S writes=%d total=%d max=%d.",
                args.mode,
                master["count"],
                master["total_bytes"],
                master["max_bytes"],
                slave["count"],
                slave["total_bytes"],
                slave["max_bytes"],
            )
        finally:
            sleep = getattr(epd, "sleep", None)
            if callable(sleep):
                sleep()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate or apply one guarded Waveshare 10.85-inch full-frame diagnostic."
    )
    parser.add_argument(
        "mode",
        choices=("full-white", "full-black", "left-black", "right-black", "live"),
    )
    parser.add_argument("--image", default="/var/lib/abu-dhabi-eink/current.png")
    parser.add_argument("--preview", help="Save the exact 1360x480 diagnostic PNG without touching hardware.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the single pattern to hardware. Omit for preview-only operation.",
    )
    parser.add_argument("--driver-lib", default="/opt/abu-dhabi-eink")
    parser.add_argument("--driver-module", default="waveshare_10in85_bw")
    parser.add_argument(
        "--vendor-lib",
        default="/opt/abu-dhabi-eink/vendor/waveshare-10in85/RaspberryPi/python/lib",
    )
    parser.add_argument("--spi-hz", type=int, default=2_000_000)
    parser.add_argument("--lock-file", default="/run/abu-dhabi-eink/display.lock")
    parser.add_argument("--service-name", default="ad-eink-display.service")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    image = load_live_frame(Path(args.image)) if args.mode == "live" else build_pattern(args.mode)
    if args.preview:
        preview = Path(args.preview)
        preview.parent.mkdir(parents=True, exist_ok=True)
        image.save(preview)
        logging.info("Saved preview to %s", preview)

    if not args.apply:
        logging.info("Preview-only mode; hardware was not opened.")
        return 0

    apply_pattern(args, image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
