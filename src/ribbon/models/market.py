from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .enums import MarketDirection


class MarketIndexItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    label: str
    current_value: float | None = None
    raw_change: float | None = None
    percent_change: float | None = None
    direction: MarketDirection = MarketDirection.FLAT
    observed_at: datetime | None = None
