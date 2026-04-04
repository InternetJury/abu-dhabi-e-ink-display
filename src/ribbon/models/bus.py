from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BusDepartureItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_id: str
    stop_title: str
    route_number: str
    destination: str
    scheduled_at: datetime | None = None
    expected_at: datetime | None = None
    due_minutes: int | None = None
    is_live: bool = False
    delay_minutes: int | None = None
    marker: str | None = None
    source: str

