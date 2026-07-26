#!/usr/bin/env python3
from __future__ import annotations

import importlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Sequence


WIDTH = 1360
HEIGHT = 480
HALF_ROW_BYTES = WIDTH // 16
HALF_BUFFER_BYTES = HALF_ROW_BYTES * HEIGHT
DEFAULT_SPI_HZ = 2_000_000
DEFAULT_VENDOR_LIB = "/opt/abu-dhabi-eink/vendor/waveshare-10in85/RaspberryPi/python/lib"
FULL_TO_PARTIAL_SETTLE_SECONDS = 2.0

logger = logging.getLogger(__name__)


def split_packed_buffer(buffer: Sequence[int], width: int = WIDTH, height: int = HEIGHT) -> tuple[list[int], list[int]]:
    """Split a row-major 1bpp MSB-first frame into 10.85in master/slave halves."""
    if width % 16 != 0:
        raise ValueError("width must be divisible by 16 so both controller halves are byte-aligned")

    row_bytes = width // 8
    half_bytes = row_bytes // 2
    expected = row_bytes * height
    if len(buffer) != expected:
        raise ValueError(f"expected {expected} packed bytes for {width}x{height}, got {len(buffer)}")

    left: list[int] = []
    right: list[int] = []
    for row in range(height):
        row_start = row * row_bytes
        mid = row_start + half_bytes
        row_end = row_start + row_bytes
        left.extend(buffer[row_start:mid])
        right.extend(buffer[mid:row_end])

    return left, right


class EPD:
    """Last-known-working adapter for the B/W Waveshare 10.85in dual-IC panel."""

    width = WIDTH
    height = HEIGHT

    def __init__(self) -> None:
        vendor_lib = os.environ.get("WAVESHARE_10IN85_VENDOR_LIB", DEFAULT_VENDOR_LIB)
        if vendor_lib and Path(vendor_lib).exists():
            sys.path.insert(0, vendor_lib)

        self._spi_hz = int(os.environ.get("WAVESHARE_10IN85_SPI_HZ", str(DEFAULT_SPI_HZ)))
        self._vendor_module = importlib.import_module("waveshare_epd.epd10in85")
        self._patch_spi_speed()
        self._epd = self._vendor_module.EPD()
        self._old_master_ready = False
        self._old_slave_ready = False

    def _patch_spi_speed(self) -> None:
        epdconfig = self._vendor_module.epdconfig
        if getattr(epdconfig, "_abu_dhabi_spi_patch_hz", None) == self._spi_hz:
            return

        original_module_init = epdconfig.module_init

        def module_init(*args, **kwargs):
            result = original_module_init(*args, **kwargs)
            implementation = getattr(epdconfig, "implementation", None)
            for spi_name in ("SPI_M", "SPI_S"):
                spi = getattr(implementation, spi_name, None)
                if spi is not None:
                    spi.max_speed_hz = self._spi_hz
            return result

        epdconfig.module_init = module_init
        epdconfig._abu_dhabi_spi_patch_hz = self._spi_hz

    def __getattr__(self, name: str):
        return getattr(self._epd, name)

    def init(self):
        self._old_master_ready = False
        self._old_slave_ready = False
        result = self._epd.init()
        # A cold boot can leave either controller on its power-on geometry even
        # though the vendor init succeeds. Reassert each 680x480 half before RAM
        # writes so master and slave advance through identical row boundaries.
        self._set_full_half_windows()
        return result

    def init_Part(self):
        self._old_master_ready = False
        self._old_slave_ready = False
        if hasattr(self._epd, "init_Part"):
            result = self._epd.init_Part()
        else:
            result = self._epd.init()
        self._set_full_half_windows()
        return result

    def getbuffer(self, image):
        return self._epd.getbuffer(image)

    def display(self, imageblack: Sequence[int]) -> None:
        master, slave = split_packed_buffer(imageblack)
        self._write_full(master, slave)
        # The panel's full waveform can leave the slave half visibly lighter.
        # Finish with one coordinated partial write so both controllers expose
        # the same final contrast after startup and periodic full refreshes.
        time.sleep(FULL_TO_PARTIAL_SETTLE_SECONDS)
        self.init_Part()
        self._write_slave_reinforcement(master, slave)

    def Clear(self) -> None:
        white = [0xFF] * HALF_BUFFER_BYTES
        self._write_full(white, white)
        self._old_master_ready = True
        self._old_slave_ready = True

    def display_Partial(self, imageblack: Sequence[int], x_start: int, y_start: int, x_end: int, y_end: int) -> None:
        if (x_start, y_start, x_end, y_end) != (0, 0, self.width, self.height):
            logger.warning(
                "Non-fullscreen partial update requested; falling back to full-frame update for %sx%s at (%s,%s).",
                x_end - x_start,
                y_end - y_start,
                x_start,
                y_start,
            )
        master, slave = split_packed_buffer(imageblack)
        self._write_partial(master, slave)

    def _write_full(self, master: Sequence[int], slave: Sequence[int]) -> None:
        self._epd.send_command_M(0x10)
        self._stream_rows(self._epd.send_data2_M, [0xFF] * HALF_BUFFER_BYTES)
        self._epd.send_command_M(0x13)
        self._stream_rows(self._epd.send_data2_M, master)

        self._epd.send_command_S(0x10)
        self._stream_rows(self._epd.send_data2_S, [0xFF] * HALF_BUFFER_BYTES)
        self._epd.send_command_S(0x13)
        self._stream_rows(self._epd.send_data2_S, slave)
        self._epd.TurnOnDisplay()

    @staticmethod
    def _stream_rows(send_data, data: Sequence[int]) -> None:
        if len(data) != HALF_BUFFER_BYTES:
            raise ValueError(f"expected {HALF_BUFFER_BYTES} bytes for one controller half, got {len(data)}")
        for row_start in range(0, HALF_BUFFER_BYTES, HALF_ROW_BYTES):
            send_data(data[row_start : row_start + HALF_ROW_BYTES])

    def _write_partial(self, master: Sequence[int], slave: Sequence[int]) -> None:
        self._set_full_half_windows()

        if not self._old_master_ready:
            self._epd.send_command_M(0x10)
            self._stream_rows(self._epd.send_data2_M, [0xFF] * len(master))
            self._old_master_ready = True

        if not self._old_slave_ready:
            self._epd.send_command_S(0x10)
            self._stream_rows(self._epd.send_data2_S, [0xFF] * len(slave))
            self._old_slave_ready = True

        self._load_new_data(master, slave)
        self._epd.TurnOnDisplay()
        self._update_old_data(master, slave)

    def _write_slave_reinforcement(self, master: Sequence[int], slave: Sequence[int]) -> None:
        """Re-drive slave black pixels while keeping the master image unchanged."""
        self._set_full_half_windows()

        # A no-op master transition keeps the shared refresh synchronized. The
        # slave receives an explicit white-to-target transition so its lighter
        # fine strokes get the same black-state drive as the master controller.
        self._epd.send_command_M(0x10)
        self._stream_rows(self._epd.send_data2_M, master)
        self._epd.send_command_S(0x10)
        self._stream_rows(self._epd.send_data2_S, [0xFF] * len(slave))

        self._load_new_data(master, slave)
        self._epd.TurnOnDisplay()
        self._update_old_data(master, slave)
        self._old_master_ready = True
        self._old_slave_ready = True

    def _set_full_half_windows(self) -> None:
        half_width = self.width // 2
        for prefix in ("M", "S"):
            send_command = getattr(self._epd, f"send_command_{prefix}")
            send_data = getattr(self._epd, f"send_data_{prefix}")
            send_command(0x61)
            send_data((half_width >> 8) & 0xFF)
            send_data(half_width & 0xFF)
            send_data((self.height >> 8) & 0xFF)
            send_data(self.height & 0xFF)
            send_command(0x62)
            send_data(0x00)
            send_data(0x00)
            send_data(0x00)
            send_data(0x00)

    def _load_new_data(self, master: Sequence[int], slave: Sequence[int]) -> None:
        self._epd.send_command_M(0x13)
        self._stream_rows(self._epd.send_data2_M, master)
        self._epd.send_command_S(0x13)
        self._stream_rows(self._epd.send_data2_S, slave)

    def _update_old_data(self, master: Sequence[int], slave: Sequence[int]) -> None:
        self._epd.send_command_M(0x10)
        self._stream_rows(self._epd.send_data2_M, master)
        self._epd.send_command_S(0x10)
        self._stream_rows(self._epd.send_data2_S, slave)
