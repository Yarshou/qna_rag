from datetime import datetime

from pydantic import field_validator

from app.schemas.base import BaseSchema


class CreateChatRequest(BaseSchema):
    title: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatResponse(BaseSchema):
    id: str
    title: str | None
    status: str
    created_at: datetime


class ChatListResponse(BaseSchema):
    items: list[ChatResponse]
    total: int
    limit: int
    offset: int
