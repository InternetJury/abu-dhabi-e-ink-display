from __future__ import annotations

from datetime import datetime

from ribbon.fixtures import load_fixture_document
from ribbon.models import HeadlineItem, MarketIndexItem, WeatherSummary
from ribbon.providers.base import BusProvider, HeadlineProvider, MarketProvider, ProviderError, WeatherProvider
from ribbon.providers.bus_darbi import normalize_darbi_departures
from ribbon.settings import SavedStop


class FixtureBusProvider(BusProvider):
    def __init__(self, fixture_name: str) -> None:
        self.document = load_fixture_document(fixture_name)

    def fetch_stop(self, stop: SavedStop, now: datetime):
        raw_items = self.document.get("raw", {}).get("bus", {}).get(stop.stop_id)
        if raw_items is None:
            raise ProviderError(f"No fixture bus data for {stop.stop_id}")
        return normalize_darbi_departures(raw_items, stop, now, source="fixture")


class FixtureWeatherProvider(WeatherProvider):
    def __init__(self, fixture_name: str) -> None:
        self.document = load_fixture_document(fixture_name)

    def fetch(self, now: datetime) -> WeatherSummary:
        weather = self.document.get("snapshot", {}).get("weather")
        if not weather:
            raise ProviderError("No fixture weather data")
        return WeatherSummary.model_validate(weather)


class FixtureHeadlineProvider(HeadlineProvider):
    def __init__(self, fixture_name: str) -> None:
        self.document = load_fixture_document(fixture_name)

    def fetch(self, limit: int = 6):
        headlines = self.document.get("snapshot", {}).get("headlines", [])
        if not headlines:
            raise ProviderError("No fixture headlines")
        return [HeadlineItem.model_validate(item) for item in headlines[:limit]]


class FixtureMarketProvider(MarketProvider):
    def __init__(self, fixture_name: str) -> None:
        self.document = load_fixture_document(fixture_name)

    def fetch(self, now: datetime) -> list[MarketIndexItem]:
        indices = self.document.get("snapshot", {}).get("market_indices", [])
        if not indices:
            raise ProviderError("No fixture market data")
        return [MarketIndexItem.model_validate(item) for item in indices]
