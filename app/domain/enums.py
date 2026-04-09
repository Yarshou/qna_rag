from enum import StrEnum


class MessageRole(StrEnum):
    """Stable roles used for persisted and internal chat messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatStatus(StrEnum):
    """Lifecycle states for a chat record."""

    ACTIVE = "active"
    DELETED = "deleted"
    FAILED = "failed"


class EventType(StrEnum):
    """Event names emitted during message processing."""

    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PROCESSING = "message_processing"
    TOOL_CALLED = "tool_called"
    MESSAGE_COMPLETED = "message_completed"
    MESSAGE_FAILED = "message_failed"
