from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WeatherSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    location_label: str
    temperature_c: float
    daily_high_c: float | None = None
    daily_low_c: float | None = None
    condition_label: str
    humidity_pct: int | None = None
    aqi_index: int | None = None
    aqi_label: str | None = None
    sunrise_local: datetime | None = None
    sunset_local: datetime | None = None
    observed_at: datetime
