from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HeadlineItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    source_name: str
    url: str
    published_at: datetime | None = None

