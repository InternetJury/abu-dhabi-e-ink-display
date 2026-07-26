from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from ribbon.models import MarketDirection, MarketIndexItem
from ribbon.providers.base import MarketProvider, ProviderError
from ribbon.settings import SETTINGS


LOCAL_TZ = ZoneInfo(SETTINGS.timezone)


class CompositeMarketProvider(MarketProvider):
    def __init__(self) -> None:
        self.cache_path = SETTINGS.cache_dir / "markets.json"

    @staticmethod
    def _direction(percent_change: float | None) -> MarketDirection:
        if percent_change is None or abs(percent_change) < 0.005:
            return MarketDirection.FLAT
        return MarketDirection.UP if percent_change > 0 else MarketDirection.DOWN

    @staticmethod
    def _parse_nse_timestamp(raw: str | None) -> datetime | None:
        if not raw:
            return None
        for date_format in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
            try:
                return datetime.strptime(raw, date_format).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            except ValueError:
                continue
        return None

    def _write_cache(self, items: list[MarketIndexItem]) -> None:
        SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(LOCAL_TZ).isoformat(),
            "items": [item.model_dump(mode="json") for item in items],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_cache(self) -> tuple[datetime | None, list[MarketIndexItem]]:
        if not self.cache_path.exists():
            raise ProviderError("No market cache available")
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"]) if payload.get("fetched_at") else None
        items = [MarketIndexItem.model_validate(item) for item in payload.get("items", [])]
        return fetched_at, items

    def _fresh_cache(self, now: datetime) -> list[MarketIndexItem] | None:
        try:
            fetched_at, items = self._read_cache()
        except ProviderError:
            return None
        if fetched_at is None:
            return None
        age_seconds = (now.astimezone(LOCAL_TZ) - fetched_at.astimezone(LOCAL_TZ)).total_seconds()
        if age_seconds <= SETTINGS.market_cache_ttl_minutes * 60:
            return items
        return None

    @classmethod
    def _parse_nse_payload(cls, payload: dict, now: datetime) -> MarketIndexItem:
        rows = payload.get("data", [])
        target = next(
            (
                row
                for row in rows
                if row.get("symbol") == "NIFTY 50"
                or row.get("identifier") == "NIFTY 50"
                or row.get("index") == "NIFTY 50"
            ),
            None,
        )
        if target is None and rows:
            target = rows[0]
        if target is None:
            raise ProviderError("NSE payload missing NIFTY 50 record")

        percent_value = target.get("pChange", target.get("percentChange"))
        raw_value = target.get("change", target.get("variation"))
        current_value_raw = target.get("lastPrice", target.get("last"))
        percent_change = float(percent_value) if percent_value is not None else None
        raw_change = float(raw_value) if raw_value is not None else None
        current_value = float(current_value_raw) if current_value_raw is not None else None
        observed_at = cls._parse_nse_timestamp(payload.get("timestamp") or target.get("lastUpdateTime")) or now
        return MarketIndexItem(
            code="NIFTY",
            label="NIFTY",
            current_value=current_value,
            raw_change=raw_change,
            percent_change=percent_change,
            direction=cls._direction(percent_change),
            observed_at=observed_at,
        )

    @classmethod
    def _parse_stooq_csv(cls, raw_csv: str, now: datetime) -> MarketIndexItem:
        rows = list(csv.reader(io.StringIO(raw_csv)))
        if not rows:
            raise ProviderError("Stooq CSV returned no rows")

        if rows[0] and rows[0][0] == "Symbol":
            dict_rows = list(csv.DictReader(io.StringIO(raw_csv)))
            if not dict_rows:
                raise ProviderError("Stooq CSV returned no data rows")
            row = dict_rows[0]
        else:
            values = rows[0]
            if len(values) < 7:
                raise ProviderError("Stooq CSV row missing required fields")
            row = {
                "Symbol": values[0],
                "Date": values[1],
                "Time": values[2],
                "Open": values[3],
                "High": values[4],
                "Low": values[5],
                "Close": values[6],
                "Volume": values[7] if len(values) > 7 else "",
            }

        close_value = row.get("Close")
        if close_value in (None, "", "N/D"):
            raise ProviderError("Stooq CSV did not return a usable close value")
        close_price = float(close_value)
        raw_change = None
        percent_change = None
        open_value = row.get("Open")
        if open_value not in (None, "", "N/D", "0"):
            open_price = float(open_value)
            raw_change = round(close_price - open_price, 2)
            if open_price:
                percent_change = round((raw_change / open_price) * 100, 2)
        observed_at = now
        if row.get("Date") and row.get("Time"):
            observed_at = datetime.strptime(
                f"{row['Date']} {row['Time']}",
                "%Y%m%d %H%M%S",
            ).replace(tzinfo=ZoneInfo("America/New_York"))
        return MarketIndexItem(
            code="SPX",
            label="S&P 500",
            current_value=close_price,
            raw_change=raw_change,
            percent_change=percent_change,
            direction=cls._direction(percent_change),
            observed_at=observed_at,
        )

    @classmethod
    def _parse_yahoo_chart_payload(cls, payload: dict, now: datetime) -> MarketIndexItem:
        results = payload.get("chart", {}).get("result") or []
        if not results:
            raise ProviderError("S&P 500 chart response returned no results")
        meta = results[0].get("meta") or {}
        current_value_raw = meta.get("regularMarketPrice")
        previous_close_raw = meta.get("chartPreviousClose", meta.get("previousClose"))
        if current_value_raw is None or previous_close_raw is None:
            raise ProviderError("S&P 500 chart response is missing price data")

        current_value = float(current_value_raw)
        previous_close = float(previous_close_raw)
        raw_change = round(current_value - previous_close, 2)
        percent_change = round((raw_change / previous_close) * 100, 2) if previous_close else None
        observed_at = now
        if meta.get("regularMarketTime") is not None:
            observed_at = datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=ZoneInfo("UTC"))

        return MarketIndexItem(
            code="SPX",
            label="S&P 500",
            current_value=current_value,
            raw_change=raw_change,
            percent_change=percent_change,
            direction=cls._direction(percent_change),
            observed_at=observed_at,
        )

    def _fetch_nifty(self, now: datetime) -> MarketIndexItem:
        headers = {
            "user-agent": SETTINGS.darbi_user_agent,
            "accept": "application/json,text/plain,*/*",
            "referer": "https://www.nseindia.com/",
        }
        response = httpx.get(
            "https://www.nseindia.com/api/allIndices",
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return self._parse_nse_payload(response.json(), now)

    def _fetch_sp500(self, now: datetime) -> MarketIndexItem:
        response = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
            params={"range": "5d", "interval": "1d"},
            headers={"user-agent": SETTINGS.darbi_user_agent},
            timeout=20,
        )
        response.raise_for_status()
        return self._parse_yahoo_chart_payload(response.json(), now)

    def fetch(self, now: datetime) -> list[MarketIndexItem]:
        cached = self._fresh_cache(now)
        if cached:
            return cached

        try:
            _, stale_items = self._read_cache()
        except Exception:
            stale_items = []
        stale_by_code = {item.code.upper(): item for item in stale_items}

        items: list[MarketIndexItem] = []
        errors: list[str] = []
        for code, fetcher in (("NIFTY", self._fetch_nifty), ("SPX", self._fetch_sp500)):
            try:
                items.append(fetcher(now))
            except Exception as exc:
                if code in stale_by_code:
                    items.append(stale_by_code[code])
                else:
                    errors.append(f"{code}: {exc}")

        if not items:
            raise ProviderError(f"Market fetch failed and cache missing: {'; '.join(errors)}")

        self._write_cache(items)
        return items
