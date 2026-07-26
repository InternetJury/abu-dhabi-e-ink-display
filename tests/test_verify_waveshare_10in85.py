from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "pi" / "verify-waveshare-10in85.py"
spec = importlib.util.spec_from_file_location("verify_waveshare_10in85", MODULE_PATH)
assert spec is not None
verify = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = verify
spec.loader.exec_module(verify)


@pytest.mark.parametrize(
    ("mode", "left", "right"),
    [
        ("full-white", 255, 255),
        ("full-black", 0, 0),
        ("left-black", 0, 255),
        ("right-black", 255, 0),
    ],
)
def test_diagnostic_patterns_address_expected_controller_half(mode: str, left: int, right: int):
    image = verify.build_pattern(mode)

    assert image.size == (1360, 480)
    assert image.getpixel((100, 100)) == left
    assert image.getpixel((1200, 100)) == right


def test_mirrored_contrast_pattern_is_pixel_identical_across_controller_halves():
    image = verify.build_pattern("mirrored-contrast")

    left = image.crop((0, 0, 680, 480))
    right = image.crop((680, 0, 1360, 480))

    assert image.mode == "1"
    assert left.tobytes() == right.tobytes()
    assert image.getpixel((679, 44)) == 0
    assert image.getpixel((680, 44)) == 0


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        ("official-full", ["init", "display"]),
        ("adapter-full-only", ["init", "write_full"]),
        ("adapter-slave-reinforced", ["init", "write_full", "init_part", "reinforce_slave"]),
        ("adapter-compound", ["init", "display"]),
        ("adapter-partial", ["init_part", "display_partial"]),
        ("clear-init-partial", ["init", "clear", "init_part", "display_partial"]),
        (
            "adapter-partial-cycle",
            ["init", "clear", "init_part", "display_partial", "display_partial", "display_partial"],
        ),
        (
            "adapter-reinit-partial-cycle",
            [
                "init",
                "clear",
                "init_part",
                "display_partial",
                "init_part",
                "display_partial",
                "init_part",
                "display_partial",
            ],
        ),
    ],
)
def test_refresh_strategies_have_explicit_non_overlapping_lifecycles(strategy: str, expected: list[str]):
    calls: list[str] = []

    class FakeEPD:
        width = 1360
        height = 480

        def init(self):
            calls.append("init")

        def init_Part(self):
            calls.append("init_part")

        def Clear(self):
            calls.append("clear")

        def display(self, _payload):
            calls.append("display")

        def display_Partial(self, _payload, _x0, _y0, _x1, _y1):
            calls.append("display_partial")

        def _write_full(self, _master, _slave):
            calls.append("write_full")

        def _write_slave_reinforcement(self, _master, _slave):
            calls.append("reinforce_slave")

    payload = [0xFF] * (1360 // 8 * 480)
    verify.execute_strategy(FakeEPD(), payload, strategy, repeat_count=3)

    assert calls == expected


def test_partial_cycle_alternates_white_and_pattern_and_finishes_on_pattern():
    payloads: list[list[int]] = []

    class FakeEPD:
        def init(self):
            pass

        def Clear(self):
            pass

        def init_Part(self):
            pass

        def display_Partial(self, payload, _x0, _y0, _x1, _y1):
            payloads.append(payload)

    pattern = [0x00, 0xAA, 0x55]
    verify.execute_strategy(FakeEPD(), pattern, "adapter-partial-cycle", repeat_count=5)

    assert payloads == [pattern, [0xFF] * 3, pattern, [0xFF] * 3, pattern]


def test_live_frame_rejects_wrong_dimensions(tmp_path: Path):
    path = tmp_path / "wrong.png"
    Image.new("1", (100, 100), 255).save(path)

    with pytest.raises(ValueError, match="Expected 1360x480"):
        verify.load_live_frame(path)


def test_hardware_apply_is_explicit_and_service_guarded():
    source = MODULE_PATH.read_text()

    assert '"--apply"' in source
    assert "assert_service_inactive(args.service_name)" in source
    assert "ExclusiveDisplayLock" in source
    assert "epd.sleep" not in source
    assert 'getattr(epd, "sleep"' in source


def test_transfer_trace_records_equal_master_and_slave_bulk_writes():
    class FakeVendor:
        def __init__(self):
            self.master = []
            self.slave = []

        def send_data2_M(self, data):
            self.master.append(bytes(data))

        def send_data2_S(self, data):
            self.slave.append(bytes(data))

    class FakeAdapter:
        def __init__(self):
            self._epd = FakeVendor()

    epd = FakeAdapter()
    trace = verify.TransferTrace()
    trace.install(epd)

    epd._epd.send_data2_M([0x00, 0xFF])
    epd._epd.send_data2_S([0xFF, 0x00])

    assert [(event.controller, event.byte_count) for event in trace.events] == [("M", 2), ("S", 2)]
    assert epd._epd.master == [b"\x00\xff"]
    assert epd._epd.slave == [b"\xff\x00"]


def test_transfer_trace_summarizes_row_sized_writes_without_per_row_logging():
    trace = verify.TransferTrace()
    trace.events = [
        verify.TransferEvent("M", 85, "a" * 64),
        verify.TransferEvent("M", 85, "b" * 64),
        verify.TransferEvent("S", 85, "c" * 64),
    ]

    assert trace.summary("M") == {"count": 2, "total_bytes": 170, "max_bytes": 85}
    assert trace.summary("S") == {"count": 1, "total_bytes": 85, "max_bytes": 85}


def test_official_driver_speed_patch_applies_after_vendor_module_init():
    class FakeSPI:
        max_speed_hz = None

    class FakeConfig:
        def __init__(self):
            self.implementation = type("Implementation", (), {"SPI_M": FakeSPI(), "SPI_S": FakeSPI()})()

        def module_init(self):
            self.implementation.SPI_M.max_speed_hz = 4_000_000
            self.implementation.SPI_S.max_speed_hz = 4_000_000
            return 0

    module = type("Vendor", (), {"epdconfig": FakeConfig()})()

    verify.patch_vendor_spi_speed(module, 2_000_000)
    result = module.epdconfig.module_init()

    assert result == 0
    assert module.epdconfig.implementation.SPI_M.max_speed_hz == 2_000_000
    assert module.epdconfig.implementation.SPI_S.max_speed_hz == 2_000_000
