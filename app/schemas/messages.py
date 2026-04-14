from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class PostMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content must not be empty.")
        return normalized


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    chat_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


class MessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class PostMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
    tool_calls_executed: int
    used_knowledge_files: list[str]
