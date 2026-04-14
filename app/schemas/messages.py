from datetime import datetime
from typing import Any

from pydantic import field_validator

from app.schemas.base import BaseSchema


class PostMessageRequest(BaseSchema):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content is required.")
        return normalized


class MessageResponse(BaseSchema):
    id: str
    chat_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


class MessageListResponse(BaseSchema):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class PostMessageResponse(BaseSchema):
    chat_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
    tool_calls_executed: int
    used_knowledge_files: list[str]
