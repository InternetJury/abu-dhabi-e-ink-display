from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .bus import BusDepartureItem
from .enums import FrequencyBand, LeaveByStatus


class NextBusHero(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_id: str
    route_number: str
    destination: str
    due_label: str
    scheduled_label: str | None = None
    confidence_label: str = "estimated"
    irregularity_flag: str | None = None


class ServiceDensityWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    window_start: datetime
    window_end: datetime
    departures_count: int
    routes_active: int
    bins: list[int] = Field(default_factory=list)


class RouteFrequencySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    route_number: str
    departures_count: int
    median_spacing_minutes: int | None = None
    band: FrequencyBand = FrequencyBand.UNKNOWN
    next_due_minutes: int | None = None


class LeaveByRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    walking_buffer_minutes: int
    leave_by_at: datetime | None = None
    target_departure_at: datetime | None = None
    status: LeaveByStatus


class StopInsightSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_id: str
    stop_title: str
    departures: list[BusDepartureItem]
    hero: NextBusHero | None = None
    density_window: ServiceDensityWindow | None = None
    frequency_summaries: list[RouteFrequencySummary] = Field(default_factory=list)
    irregularity_summary: list[str] = Field(default_factory=list)
    leave_by: LeaveByRecommendation | None = None


class MultiStopSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    stops: list[StopInsightSnapshot] = Field(default_factory=list)


class CityPulseSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary_line: str
    detail_lines: list[str] = Field(default_factory=list)

