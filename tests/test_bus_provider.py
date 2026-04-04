from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ribbon.models import BusDepartureItem
from ribbon.providers.bus_darbi import DarbiBusProvider, filter_departures_for_stop
from ribbon.settings import SavedStop


TZ = ZoneInfo("Asia/Dubai")


def test_filter_departures_for_stop_prefers_exact_stop_code():
    raw_items = [
        {"Stop": {"StopID": "00513A"}, "Line": {"Number": "7"}},
        {"Stop": {"StopID": "00513B"}, "Line": {"Number": "24"}},
    ]
    filtered = filter_departures_for_stop(raw_items, "00513B")
    assert len(filtered) == 1
    assert filtered[0]["Stop"]["StopID"] == "00513B"


def test_darbi_provider_normalizes_live_stop_code_search(tmp_path):
    provider = DarbiBusProvider(use_browser_fallback=False)
    provider.cache_path = tmp_path / "bus_departures.json"
    provider.rca_log_path = tmp_path / "darbi_rca.jsonl"

    stop = SavedStop("00513B", "Aster Pharmacy")
    now = datetime(2026, 4, 4, 22, 0, tzinfo=TZ)

    def fake_fetch(text: str, info: str | None = None):
        return (
            "https://darbi.example/mmjpv5",
            {
                "Departures": [
                    {
                        "Stop": {"StopID": "00513A", "Id": "1000512", "Name": "Aster Pharmacy A"},
                        "Line": {"Number": "7", "Destination": "Other"},
                        "Time": "22:05",
                        "Remaining": 5,
                    },
                    {
                        "Stop": {"StopID": "00513B", "Id": "1000513", "Name": "Aster Pharmacy"},
                        "Line": {"Number": "24", "Destination": "Central Terminal"},
                        "Time": "22:07",
                        "Remaining": 7,
                        "IsRealtime": True,
                        "delayTime": 2,
                    },
                ]
            },
        )

    provider._fetch_mmjpv5_payload = fake_fetch  # type: ignore[method-assign]

    items = provider.fetch_stop(stop, now)
    assert len(items) == 1
    assert items[0].route_number == "24"
    assert items[0].stop_id == "00513B"
    status = provider.get_last_status("00513B")
    assert status is not None
    assert status.internal_stop_id == "1000513"


def test_darbi_provider_uses_cached_board_when_live_fetch_fails(tmp_path):
    provider = DarbiBusProvider(use_browser_fallback=True)
    provider.cache_path = tmp_path / "bus_departures.json"
    provider.rca_log_path = tmp_path / "darbi_rca.jsonl"

    stop = SavedStop("00513B", "Aster Pharmacy")
    cached_at = datetime(2026, 4, 4, 21, 55, tzinfo=TZ)
    cached_items = [
        BusDepartureItem(
            stop_id="00513B",
            stop_title="Aster Pharmacy",
            route_number="24",
            destination="Central Terminal",
            scheduled_at=cached_at + timedelta(minutes=8),
            expected_at=cached_at + timedelta(minutes=8),
            due_minutes=8,
            is_live=True,
            delay_minutes=0,
            marker=None,
            source="cache",
        )
    ]
    provider._write_cache(stop, cached_items, cached_at, internal_stop_id="1000513", stop_name=stop.title)
    provider._fetch_mmjpv5_payload = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("400"))  # type: ignore[method-assign]
    provider._fetch_browser_departures = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no widget"))  # type: ignore[method-assign]

    items = provider.fetch_stop(stop, cached_at + timedelta(minutes=10))
    assert len(items) == 1
    assert items[0].route_number == "24"
    status = provider.get_last_status("00513B")
    assert status is not None
    assert status.used_cache is True
    assert status.note() is not None
