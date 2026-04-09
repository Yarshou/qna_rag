from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    chat_id: str
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class EventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EventResponse]
