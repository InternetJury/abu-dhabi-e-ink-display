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
import time

try:
    import fcntl
except ImportError:  # Windows can still validate previews; hardware apply is Linux-only.
    fcntl = None

from PIL import Image, ImageDraw, ImageFont


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


def patch_vendor_spi_speed(vendor_module, spi_hz: int) -> None:
    epdconfig = vendor_module.epdconfig
    if getattr(epdconfig, "_contrast_diagnostic_spi_hz", None) == spi_hz:
        return

    original_module_init = epdconfig.module_init

    def module_init(*args, **kwargs):
        result = original_module_init(*args, **kwargs)
        implementation = getattr(epdconfig, "implementation", None)
        for spi_name in ("SPI_M", "SPI_S"):
            spi = getattr(implementation, spi_name, None)
            if spi is not None:
                spi.max_speed_hz = spi_hz
        return result

    epdconfig.module_init = module_init
    epdconfig._contrast_diagnostic_spi_hz = spi_hz


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
    if mode == "mirrored-contrast":
        half = _build_contrast_half()
        image.paste(half, (0, 0))
        image.paste(half, (WIDTH // 2, 0))
        return image
    raise ValueError(f"Unsupported diagnostic mode: {mode}")


def _load_diagnostic_font(size: int):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _build_contrast_half() -> Image.Image:
    half_width = WIDTH // 2
    image = Image.new("1", (half_width, HEIGHT), 255)
    draw = ImageDraw.Draw(image)

    # The same full-width rules terminate at both sides of the controller seam.
    draw.line((0, 44, half_width - 1, 44), fill=0, width=1)
    draw.line((0, 64, half_width - 1, 64), fill=0, width=2)
    draw.line((0, 86, half_width - 1, 86), fill=0, width=3)

    small = _load_diagnostic_font(12)
    medium = _load_diagnostic_font(16)
    draw.text((24, 104), "LAST UPDATED 26 JUL 21:59", font=small, fill=0)
    draw.text((24, 134), "26 JUL 21:59", font=small, fill=0)
    draw.text((24, 168), "21:59", font=medium, fill=0)
    draw.text((170, 168), "SCHEDULED 21:59", font=medium, fill=0)

    draw.rectangle((24, 218, 154, 278), fill=0)
    draw.rectangle((180, 218, 310, 278), outline=0, width=1)
    draw.rectangle((336, 218, 466, 278), outline=0, width=2)
    draw.rectangle((492, 218, 622, 278), outline=0, width=3)

    for x in range(24, 624, 8):
        draw.line((x, 316, x, 396), fill=0, width=1 if (x // 8) % 2 else 2)
    for y in range(420, 456, 4):
        draw.line((24, y, 622, y), fill=0, width=1)
    return image


def split_payload_halves(payload: list[int] | bytes | bytearray) -> tuple[list[int], list[int]]:
    row_bytes = WIDTH // 8
    half_row_bytes = row_bytes // 2
    expected = row_bytes * HEIGHT
    if len(payload) != expected:
        raise ValueError(f"Expected {expected} packed bytes, got {len(payload)}")

    master: list[int] = []
    slave: list[int] = []
    for row in range(HEIGHT):
        start = row * row_bytes
        middle = start + half_row_bytes
        end = start + row_bytes
        master.extend(payload[start:middle])
        slave.extend(payload[middle:end])
    return master, slave


def execute_strategy(epd, payload, strategy: str, *, repeat_count: int = 5) -> None:
    if strategy in {"official-full", "adapter-compound"}:
        epd.init()
        epd.display(payload)
        return
    if strategy == "adapter-full-only":
        epd.init()
        master, slave = split_payload_halves(payload)
        epd._write_full(master, slave)
        return
    if strategy == "adapter-slave-reinforced":
        epd.init()
        master, slave = split_payload_halves(payload)
        epd._write_full(master, slave)
        epd.init_Part()
        epd._write_slave_reinforcement(master, slave)
        return
    if strategy == "adapter-partial":
        epd.init_Part()
        epd.display_Partial(payload, 0, 0, WIDTH, HEIGHT)
        return
    if strategy == "clear-init-partial":
        epd.init()
        epd.Clear()
        epd.init_Part()
        epd.display_Partial(payload, 0, 0, WIDTH, HEIGHT)
        return
    if strategy == "adapter-partial-cycle":
        if repeat_count < 1 or repeat_count % 2 == 0:
            raise ValueError("Partial cycle repeat count must be a positive odd number")
        white_payload = [0xFF] * len(payload)
        epd.init()
        epd.Clear()
        epd.init_Part()
        for index in range(repeat_count):
            frame = payload if index % 2 == 0 else white_payload
            epd.display_Partial(frame, 0, 0, WIDTH, HEIGHT)
        return
    if strategy == "adapter-reinit-partial-cycle":
        if repeat_count < 1 or repeat_count % 2 == 0:
            raise ValueError("Partial cycle repeat count must be a positive odd number")
        white_payload = [0xFF] * len(payload)
        epd.init()
        epd.Clear()
        for index in range(repeat_count):
            epd.init_Part()
            frame = payload if index % 2 == 0 else white_payload
            epd.display_Partial(frame, 0, 0, WIDTH, HEIGHT)
        return
    raise ValueError(f"Unsupported refresh strategy: {strategy}")


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
    sys.path.insert(0, args.vendor_lib)

    with ExclusiveDisplayLock(Path(args.lock_file)):
        module_name = "waveshare_epd.epd10in85" if args.strategy == "official-full" else args.driver_module
        module = importlib.import_module(module_name)
        if args.strategy == "official-full":
            patch_vendor_spi_speed(module, args.spi_hz)
        epd = module.EPD()
        trace = TransferTrace()
        trace.install(epd)
        try:
            started_at = time.monotonic()
            payload = epd.getbuffer(image)
            execute_strategy(epd, payload, args.strategy, repeat_count=args.repeat_count)
            elapsed = time.monotonic() - started_at
            master = trace.summary("M")
            slave = trace.summary("S")
            logging.info(
                "Applied %s with %s in %.2fs; "
                "M writes=%d total=%d max=%d; S writes=%d total=%d max=%d.",
                args.mode,
                args.strategy,
                elapsed,
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
        choices=("full-white", "full-black", "left-black", "right-black", "mirrored-contrast", "live"),
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
        "--strategy",
        choices=(
            "official-full",
            "adapter-full-only",
            "adapter-slave-reinforced",
            "adapter-compound",
            "adapter-partial",
            "clear-init-partial",
            "adapter-partial-cycle",
            "adapter-reinit-partial-cycle",
        ),
        default="adapter-compound",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=5,
        help="Positive odd update count for adapter-partial-cycle; the final frame is the requested pattern.",
    )
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
