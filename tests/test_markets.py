from datetime import datetime
from zoneinfo import ZoneInfo

from ribbon.models import MarketDirection, MarketIndexItem
from ribbon.providers.markets import CompositeMarketProvider
from ribbon.settings import SETTINGS


TZ = ZoneInfo("Asia/Dubai")


def test_parse_nse_payload_returns_nifty_item():
    payload = {
        "timestamp": "02-Apr-2026 16:00:00",
        "data": [
            {
                "symbol": "NIFTY 50",
                "identifier": "NIFTY 50",
                "lastPrice": 22713.45,
                "change": 33.7,
                "pChange": 0.15,
            }
        ],
    }
    item = CompositeMarketProvider._parse_nse_payload(payload, datetime(2026, 4, 2, 17, 0, tzinfo=TZ))
    assert item.code == "NIFTY"
    assert item.direction == MarketDirection.UP
    assert item.current_value == 22713.45
    assert item.raw_change == 33.7
    assert item.percent_change == 0.15


def test_parse_stooq_csv_returns_sp500_item():
    raw_csv = "^SPX,20260402,230000,6512.61,6601.91,6474.94,6582.69,2728840298,\n"
    item = CompositeMarketProvider._parse_stooq_csv(raw_csv, datetime(2026, 4, 3, 1, 0, tzinfo=TZ))
    assert item.label == "S&P 500"
    assert item.direction == MarketDirection.UP
    assert item.current_value == 6582.69
    assert item.raw_change is not None
    assert item.percent_change is not None


def test_market_provider_uses_cache_when_live_fetch_fails(tmp_path):
    provider = CompositeMarketProvider()
    provider.cache_path = tmp_path / "markets.json"
    cached_items = [
        MarketIndexItem(
            code="NIFTY",
            label="NIFTY",
            percent_change=0.22,
            direction=MarketDirection.UP,
            observed_at=datetime(2026, 4, 2, 16, 0, tzinfo=TZ),
        ),
        MarketIndexItem(
            code="SPX",
            label="S&P 500",
            percent_change=-0.11,
            direction=MarketDirection.DOWN,
            observed_at=datetime(2026, 4, 2, 23, 0, tzinfo=TZ),
        ),
    ]
    provider._write_cache(cached_items)
    provider._fetch_nifty = lambda now: (_ for _ in ()).throw(RuntimeError("down"))  # type: ignore[method-assign]
    provider._fetch_sp500 = lambda now: (_ for _ in ()).throw(RuntimeError("down"))  # type: ignore[method-assign]

    items = provider.fetch(datetime(2026, 4, 3, 9, 0, tzinfo=TZ))
    assert len(items) == 2
    assert items[0].code == "NIFTY"


def test_refresh_contract_settings_match_requested_cadence():
    assert SETTINGS.render_interval_seconds == 60
    assert SETTINGS.weather_cache_ttl_minutes == 10
    assert SETTINGS.market_cache_ttl_minutes == 15
    assert SETTINGS.headline_cache_ttl_minutes == 60
