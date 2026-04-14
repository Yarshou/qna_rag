from datetime import datetime
from typing import Any

from app.schemas.base import BaseSchema


class EventResponse(BaseSchema):
    id: str
    chat_id: str
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class EventListResponse(BaseSchema):
    items: list[EventResponse]
