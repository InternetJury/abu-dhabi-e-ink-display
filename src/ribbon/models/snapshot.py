from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import ModeName, RefreshHint
from .headlines import HeadlineItem
from .insights import CityPulseSummary, MultiStopSnapshot, StopInsightSnapshot
from .market import MarketIndexItem
from .weather import WeatherSummary


class RibbonSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ModeName
    generated_at: datetime
    timezone: str
    refresh_hint: RefreshHint
    weather: WeatherSummary
    headlines: list[HeadlineItem] = Field(default_factory=list)
    market_indices: list[MarketIndexItem] = Field(default_factory=list)
    primary_stop: StopInsightSnapshot | None = None
    multi_stop: MultiStopSnapshot | None = None
    city_summary: CityPulseSummary | None = None
    degraded_reason: str | None = None
