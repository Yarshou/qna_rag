from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class CreateChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None
    status: str
    created_at: datetime


class ChatListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChatResponse]


class DeleteChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: bool
