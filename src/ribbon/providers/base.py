from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ribbon.models import BusDepartureItem, HeadlineItem, MarketIndexItem, WeatherSummary
from ribbon.settings import SavedStop


class ProviderError(RuntimeError):
    """Raised when a provider cannot return usable data."""


class BusProvider(ABC):
    @abstractmethod
    def fetch_stop(self, stop: SavedStop, now: datetime) -> list[BusDepartureItem]:
        raise NotImplementedError

    def fetch_many(self, stops: list[SavedStop], now: datetime) -> dict[str, list[BusDepartureItem]]:
        return {stop.stop_id: self.fetch_stop(stop, now) for stop in stops}


class HeadlineProvider(ABC):
    @abstractmethod
    def fetch(self, limit: int = 6) -> list[HeadlineItem]:
        raise NotImplementedError


class WeatherProvider(ABC):
    @abstractmethod
    def fetch(self, now: datetime) -> WeatherSummary:
        raise NotImplementedError


class MarketProvider(ABC):
    @abstractmethod
    def fetch(self, now: datetime) -> list[MarketIndexItem]:
        raise NotImplementedError


class ChainedBusProvider(BusProvider):
    def __init__(self, *providers: BusProvider) -> None:
        self.providers = providers

    def fetch_stop(self, stop: SavedStop, now: datetime) -> list[BusDepartureItem]:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return provider.fetch_stop(stop, now)
            except Exception as exc:  # pragma: no cover - exercised via integration path
                last_error = exc
        raise ProviderError(f"All bus providers failed for {stop.stop_id}: {last_error}")
