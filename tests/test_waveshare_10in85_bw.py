from __future__ import annotations

import importlib.util
import types
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


def test_default_spi_speed_matches_last_known_working_runtime():
    assert waveshare_10in85_bw.DEFAULT_SPI_HZ == 2_000_000


def test_full_display_loads_both_halves_before_one_shared_refresh(monkeypatch):
    calls: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    class FakeVendorEPD:
        def send_command_M(self, command):
            calls.append(("command_m", command))

        def send_command_S(self, command):
            calls.append(("command_s", command))

        def send_data2_M(self, data):
            calls.append(("data_m", len(data), data[0]))

        def send_data2_S(self, data):
            calls.append(("data_s", len(data), data[0]))

        def TurnOnDisplay(self):
            calls.append(("refresh",))

    fake_module = types.SimpleNamespace(EPD=FakeVendorEPD, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)

    adapter = waveshare_10in85_bw.EPD()
    half_size = waveshare_10in85_bw.HALF_BUFFER_BYTES
    adapter._write_full([0x11] * half_size, [0x22] * half_size)

    refresh_index = calls.index(("refresh",))
    command_calls = [call for call in calls[:refresh_index] if call[0].startswith("command_")]
    assert command_calls == [
        ("command_m", 0x10),
        ("command_m", 0x13),
        ("command_s", 0x10),
        ("command_s", 0x13),
    ]
    assert calls[1] == ("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)
    assert calls[482] == ("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0x11)
    assert calls[963] == ("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)
    assert calls[1444] == ("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0x22)
    assert calls.count(("refresh",)) == 1
    assert calls[-1] == ("refresh",)


def test_public_full_display_finishes_with_coordinated_partial_normalization(monkeypatch):
    events: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    fake_module = types.SimpleNamespace(EPD=object, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)
    monkeypatch.setattr(waveshare_10in85_bw.time, "sleep", lambda seconds: events.append(("settle", seconds)))

    adapter = waveshare_10in85_bw.EPD()
    monkeypatch.setattr(adapter, "_write_full", lambda master, slave: events.append(("full", master[0], slave[0])))
    monkeypatch.setattr(adapter, "init_Part", lambda: events.append(("init_part",)))
    monkeypatch.setattr(adapter, "_write_partial", lambda master, slave: events.append(("partial", master[0], slave[0])))

    payload = []
    for _row in range(waveshare_10in85_bw.HEIGHT):
        payload.extend([0x11] * waveshare_10in85_bw.HALF_ROW_BYTES)
        payload.extend([0x22] * waveshare_10in85_bw.HALF_ROW_BYTES)
    adapter.display(payload)

    assert events == [
        ("full", 0x11, 0x22),
        ("settle", waveshare_10in85_bw.FULL_TO_PARTIAL_SETTLE_SECONDS),
        ("init_part",),
        ("partial", 0x11, 0x22),
    ]


def test_adapter_does_not_override_vendor_chip_select_or_init_sequence():
    source = MODULE_PATH.read_text()

    assert "no_cs = True" not in source
    assert "_patch_manual_chip_selects" not in source
    assert "_patch_shared_controller_commands" not in source
    assert "_init_registers" not in source
    assert "_deselect_controllers" not in source


def test_init_reasserts_full_geometry_for_both_controllers(monkeypatch):
    calls: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    class FakeVendorEPD:
        def init(self):
            calls.append(("init",))
            return 0

        def send_command_M(self, command):
            calls.append(("command_m", command))

        def send_command_S(self, command):
            calls.append(("command_s", command))

        def send_data_M(self, data):
            calls.append(("data_m", data))

        def send_data_S(self, data):
            calls.append(("data_s", data))

    fake_module = types.SimpleNamespace(EPD=FakeVendorEPD, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)

    adapter = waveshare_10in85_bw.EPD()
    adapter.init()

    assert calls == [
        ("init",),
        ("command_m", 0x61),
        ("data_m", 0x02),
        ("data_m", 0xA8),
        ("data_m", 0x01),
        ("data_m", 0xE0),
        ("command_m", 0x62),
        ("data_m", 0x00),
        ("data_m", 0x00),
        ("data_m", 0x00),
        ("data_m", 0x00),
        ("command_s", 0x61),
        ("data_s", 0x02),
        ("data_s", 0xA8),
        ("data_s", 0x01),
        ("data_s", 0xE0),
        ("command_s", 0x62),
        ("data_s", 0x00),
        ("data_s", 0x00),
        ("data_s", 0x00),
        ("data_s", 0x00),
    ]


def test_full_display_streams_old_and_new_ram_in_row_sized_transfers(monkeypatch):
    calls: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    class FakeVendorEPD:
        def send_command_M(self, command):
            calls.append(("command_m", command))

        def send_command_S(self, command):
            calls.append(("command_s", command))

        def send_data2_M(self, data):
            calls.append(("data_m", len(data)))

        def send_data2_S(self, data):
            calls.append(("data_s", len(data)))

        def TurnOnDisplay(self):
            calls.append(("refresh",))

    fake_module = types.SimpleNamespace(EPD=FakeVendorEPD, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)

    adapter = waveshare_10in85_bw.EPD()
    half_row_bytes = waveshare_10in85_bw.WIDTH // 16
    half_size = half_row_bytes * waveshare_10in85_bw.HEIGHT
    adapter._write_full([0x11] * half_size, [0x22] * half_size)

    transfer_lengths = [call[1] for call in calls if call[0] in {"data_m", "data_s"}]
    assert max(transfer_lengths) == half_row_bytes
    assert sum(1 for call in calls if call == ("data_m", half_row_bytes)) == 960
    assert sum(1 for call in calls if call == ("data_s", half_row_bytes)) == 960
    assert calls[-1] == ("refresh",)


def test_partial_display_streams_both_halves_before_refresh_and_updates_old_ram(monkeypatch):
    calls: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    class FakeVendorEPD:
        def send_command_M(self, command):
            calls.append(("command_m", command))

        def send_command_S(self, command):
            calls.append(("command_s", command))

        def send_data_M(self, data):
            calls.append(("geometry_m", data))

        def send_data_S(self, data):
            calls.append(("geometry_s", data))

        def send_data2_M(self, data):
            calls.append(("data_m", len(data), data[0]))

        def send_data2_S(self, data):
            calls.append(("data_s", len(data), data[0]))

        def TurnOnDisplay(self):
            calls.append(("refresh",))

    fake_module = types.SimpleNamespace(EPD=FakeVendorEPD, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)

    adapter = waveshare_10in85_bw.EPD()
    half_size = waveshare_10in85_bw.HALF_BUFFER_BYTES
    adapter._write_partial([0x11] * half_size, [0x22] * half_size)

    refresh_index = calls.index(("refresh",))
    before_refresh = calls[:refresh_index]
    after_refresh = calls[refresh_index + 1 :]
    assert ("command_m", 0x10) in before_refresh
    assert ("command_s", 0x10) in before_refresh
    assert ("command_m", 0x13) in before_refresh
    assert ("command_s", 0x13) in before_refresh
    assert before_refresh.count(("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)) == 480
    assert before_refresh.count(("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)) == 480
    assert before_refresh.count(("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0x11)) == 480
    assert before_refresh.count(("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0x22)) == 480
    assert after_refresh[0] == ("command_m", 0x10)
    assert after_refresh[481] == ("command_s", 0x10)
    assert after_refresh.count(("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0x11)) == 480
    assert after_refresh.count(("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0x22)) == 480


def test_clear_uses_bounded_dual_controller_transfers(monkeypatch):
    calls: list[tuple] = []

    class FakeConfig:
        def __init__(self):
            self.implementation = types.SimpleNamespace(
                SPI_M=types.SimpleNamespace(max_speed_hz=None),
                SPI_S=types.SimpleNamespace(max_speed_hz=None),
            )

        def module_init(self):
            return 0

    class FakeVendorEPD:
        def send_command_M(self, command):
            calls.append(("command_m", command))

        def send_command_S(self, command):
            calls.append(("command_s", command))

        def send_data2_M(self, data):
            calls.append(("data_m", len(data), data[0]))

        def send_data2_S(self, data):
            calls.append(("data_s", len(data), data[0]))

        def TurnOnDisplay(self):
            calls.append(("refresh",))

    fake_module = types.SimpleNamespace(EPD=FakeVendorEPD, epdconfig=FakeConfig())
    monkeypatch.setattr(waveshare_10in85_bw.importlib, "import_module", lambda _name: fake_module)

    adapter = waveshare_10in85_bw.EPD()
    adapter.Clear()

    assert calls.count(("data_m", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)) == 960
    assert calls.count(("data_s", waveshare_10in85_bw.HALF_ROW_BYTES, 0xFF)) == 960
    assert calls[-1] == ("refresh",)
