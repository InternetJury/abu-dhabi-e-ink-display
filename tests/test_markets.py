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


def test_parse_current_nse_all_indices_payload_returns_nifty_item():
    payload = {
        "timestamp": "24-Jul-2026 15:30",
        "data": [
            {
                "index": "NIFTY 50",
                "last": 23767.45,
                "variation": -102.15,
                "percentChange": -0.43,
            }
        ],
    }

    item = CompositeMarketProvider._parse_nse_payload(payload, datetime(2026, 7, 24, 16, 0, tzinfo=TZ))

    assert item.current_value == 23767.45
    assert item.raw_change == -102.15
    assert item.percent_change == -0.43
    assert item.direction == MarketDirection.DOWN


def test_parse_yahoo_chart_payload_returns_sp500_item():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 7411.98,
                        "chartPreviousClose": 7457.69,
                        "regularMarketTime": 1784928395,
                    }
                }
            ]
        }
    }

    item = CompositeMarketProvider._parse_yahoo_chart_payload(payload, datetime(2026, 7, 24, 20, 0, tzinfo=TZ))

    assert item.current_value == 7411.98
    assert item.raw_change == -45.71
    assert item.percent_change == -0.61
    assert item.direction == MarketDirection.DOWN


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


def test_market_provider_keeps_successful_source_when_other_source_fails(tmp_path):
    provider = CompositeMarketProvider()
    provider.cache_path = tmp_path / "markets.json"
    nifty = MarketIndexItem(
        code="NIFTY",
        label="NIFTY",
        current_value=23767.45,
        raw_change=-102.15,
        percent_change=-0.43,
        direction=MarketDirection.DOWN,
        observed_at=datetime(2026, 7, 24, 15, 30, tzinfo=TZ),
    )
    provider._fetch_nifty = lambda now: nifty  # type: ignore[method-assign]
    provider._fetch_sp500 = lambda now: (_ for _ in ()).throw(RuntimeError("down"))  # type: ignore[method-assign]

    items = provider.fetch(datetime(2026, 7, 26, 20, 0, tzinfo=TZ))

    assert items == [nifty]


def test_refresh_contract_settings_match_requested_cadence():
    assert SETTINGS.render_interval_seconds == 60
    assert SETTINGS.weather_cache_ttl_minutes == 10
    assert SETTINGS.market_cache_ttl_minutes == 15
    assert SETTINGS.headline_cache_ttl_minutes == 30
