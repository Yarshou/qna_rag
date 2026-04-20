"""Core types entities shared across repository and service boundaries.

Each entity follows the same two-method contract:

* ``from_mapping(data)`` — factory that builds a typed entity from a raw
  ``dict`` (typically an ``aiosqlite.Row`` cast to a mapping).  String
  coercions like ``str(data["id"])`` are intentionally defensive: SQLite
  can return integer row IDs even when the column is declared TEXT, and
  the coercion keeps the types layer free of database-type surprises.

* ``to_dict()`` — serialises the entity to a plain ``dict`` with stable
  string representations (ISO 8601 for timestamps, ``.value`` for enums).
  Used when passing types objects to the repository write path or logging.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.types.enums import ChatStatus, EventType, MessageRole
from app.types.utils import JsonMap, optional_json_map, parse_datetime


@dataclass(slots=True)
class Chat:
    """Internal chat entity shared across repository and service boundaries."""

    id: str
    created_at: datetime
    title: str | None
    status: ChatStatus

    def __post_init__(self) -> None:
        """Coerce incoming values into the types's timestamp and enum types."""

        self.created_at = parse_datetime(self.created_at)
        self.status = ChatStatus(self.status)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Chat":
        """Build a chat from a repository-style mapping."""

        return cls(
            id=str(data["id"]),
            created_at=data["created_at"],
            title=data.get("title"),
            status=data.get("status") or ChatStatus.ACTIVE,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the chat into a plain mapping with stable string values."""

        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "title": self.title,
            "status": self.status.value,
        }


@dataclass(slots=True)
class Message:
    """Internal message entity for persisted chat messages."""

    id: str
    chat_id: str
    role: MessageRole
    content: str
    created_at: datetime
    metadata: JsonMap | None = None

    def __post_init__(self) -> None:
        """Coerce incoming values into the types's timestamp and enum types."""

        self.role = MessageRole(self.role)
        self.created_at = parse_datetime(self.created_at)
        self.metadata = optional_json_map(self.metadata)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Message":
        """Build a message from a repository-style mapping."""

        return cls(
            id=str(data["id"]),
            chat_id=str(data["chat_id"]),
            role=data["role"],
            content=str(data["content"]),
            created_at=data["created_at"],
            metadata=data.get("metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message into a plain mapping with stable string values."""

        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ChatEvent:
    """Internal event entity representing message-processing milestones."""

    id: str
    chat_id: str
    event_type: EventType
    payload: JsonMap | None
    created_at: datetime

    def __post_init__(self) -> None:
        """Coerce incoming values into the types's timestamp and enum types."""

        self.event_type = EventType(self.event_type)
        self.created_at = parse_datetime(self.created_at)
        self.payload = optional_json_map(self.payload)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ChatEvent":
        """Build an event from a repository-style mapping."""

        return cls(
            id=str(data["id"]),
            chat_id=str(data["chat_id"]),
            event_type=data["event_type"],
            payload=data.get("payload"),
            created_at=data["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event into a plain mapping with stable string values."""

        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class KnowledgeFileRef:
    """Reference metadata for a knowledge-base file selected by retrieval."""

    id: str
    filename: str
    path: str
    checksum: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Normalize the optional file timestamp when present."""

        if self.updated_at is not None:
            self.updated_at = parse_datetime(self.updated_at)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "KnowledgeFileRef":
        """Build a knowledge file reference from a plain mapping."""

        return cls(
            id=str(data["id"]),
            filename=str(data["filename"]),
            path=str(data["path"]),
            checksum=data.get("checksum"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the knowledge file reference into a plain mapping."""

        return {
            "id": self.id,
            "filename": self.filename,
            "path": self.path,
            "checksum": self.checksum,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }
