from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "pi" / "waveshare_10in85_bw.py"
spec = importlib.util.spec_from_file_location("waveshare_10in85_bw", MODULE_PATH)
assert spec is not None
waveshare_10in85_bw = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(waveshare_10in85_bw)


def test_split_packed_buffer_preserves_row_order_across_dual_controllers():
    payload = [1, 2, 3, 4, 5, 6, 7, 8]

    master, slave = waveshare_10in85_bw.split_packed_buffer(payload, width=32, height=2)

    assert master == [1, 2, 5, 6]
    assert slave == [3, 4, 7, 8]


def test_split_packed_buffer_rejects_non_byte_aligned_controller_halves():
    with pytest.raises(ValueError, match="width must be divisible by 16"):
        waveshare_10in85_bw.split_packed_buffer([0, 1, 2], width=24, height=1)


def test_split_packed_buffer_rejects_incomplete_frames():
    with pytest.raises(ValueError, match="expected 81600 packed bytes"):
        waveshare_10in85_bw.split_packed_buffer([0] * 81599)
