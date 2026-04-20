"""Shared fixtures and fake service classes for API integration tests.

The API integration suite exercises the full FastAPI stack through
``TestClient`` while substituting business-logic services with hand-rolled
fakes.  This module centralises those fakes and their fixtures so that
``test_api.py`` and ``test_api_errors.py`` share one source of truth.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from app.shared_types import Chat, ChatEvent, ChatStatus, EventType, Message, MessageRole
from app.config.app import app
from app.services import ChatNotFoundError, MessageProcessingResult


class FakeChatService:
    """Chat service backed by a single configurable chat row."""

    def __init__(self, chat: Chat | None) -> None:
        self._chat = chat

    async def create_chat(self, title: str | None = None) -> Chat:
        if self._chat is None:
            return Chat(
                id="new-chat",
                title=title,
                status=ChatStatus.ACTIVE,
                created_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            )
        return replace(self._chat, title=title)

    async def list_chats(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Chat], int]:
        items = [] if self._chat is None else [self._chat]
        return items, len(items)

    async def get_chat(self, chat_id: str) -> Chat | None:
        if self._chat is None or self._chat.id != chat_id:
            return None
        return self._chat

    async def delete_chat(self, chat_id: str) -> bool:
        return self._chat is not None and self._chat.id == chat_id


class FakeChatServiceMissing:
    """Always reports chats as absent; causes 404 on delete and get paths."""

    async def create_chat(self, title: str | None = None) -> Chat:
        return Chat(
            id="new-chat",
            title=title,
            status=ChatStatus.ACTIVE,
            created_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
        )

    async def list_chats(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Chat], int]:
        return [], 0

    async def get_chat(self, chat_id: str) -> Chat | None:
        return None

    async def delete_chat(self, chat_id: str) -> bool:
        return False


class FakeChatServiceBroken:
    """Raises on every mutating or listing call; exercises 500 branches."""

    async def create_chat(self, title: str | None = None) -> Chat:
        raise RuntimeError("DB connection failed")

    async def list_chats(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Chat], int]:
        raise RuntimeError("DB connection failed")

    async def get_chat(self, chat_id: str) -> Chat | None:
        return None

    async def delete_chat(self, chat_id: str) -> bool:
        raise RuntimeError("DB connection failed")


class FakeMessageService:
    """Happy-path message service configured with a deterministic processing result."""

    def __init__(self, messages: list[Message], processing_result: MessageProcessingResult) -> None:
        self._messages = messages
        self._processing_result = processing_result

    async def list_messages(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        if chat_id != self._processing_result.chat_id:
            raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")
        return self._messages, len(self._messages)

    async def post_user_message(self, chat_id: str, content: str) -> MessageProcessingResult:
        if chat_id != self._processing_result.chat_id:
            raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")
        return self._processing_result


class FakeMessageServiceRaises:
    """Raises the caller-supplied exception from ``post_user_message``."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def list_messages(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")

    async def post_user_message(self, chat_id: str, content: str) -> MessageProcessingResult:
        raise self._error


class FakeNotificationService:
    """Notification service that returns a pre-seeded list of events."""

    def __init__(self, events: list[ChatEvent]) -> None:
        self._events = events

    async def list_events(
        self,
        chat_id: str,
        *,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[ChatEvent]:
        items = [event for event in self._events if event.chat_id == chat_id]
        if since is not None:
            items = [event for event in items if event.created_at.isoformat() >= since]
        if limit is not None:
            items = items[:limit]
        return items


class FakeNotificationServiceEmpty:
    """Notification service that returns empty results from every method."""

    async def list_events(
        self,
        chat_id: str,
        *,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[ChatEvent]:
        return []

    async def list_events_after(
        self,
        chat_id: str,
        *,
        after_created_at: str | None = None,
        after_id: str | None = None,
        limit: int | None = None,
    ) -> list[ChatEvent]:
        return []

    async def get_event(self, chat_id: str, event_id: str) -> ChatEvent | None:
        return None

    async def get_latest_event(self, chat_id: str) -> ChatEvent | None:
        return None


@pytest.fixture
def client():
    """FastAPI TestClient with a clean ``dependency_overrides`` mapping."""
    with TestClient(app) as test_client:
        app.dependency_overrides.clear()
        yield test_client
        app.dependency_overrides.clear()


@pytest.fixture
def sample_chat() -> Chat:
    return Chat(
        id="chat-1",
        title="Existing chat",
        status=ChatStatus.ACTIVE,
        created_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_messages(sample_chat: Chat) -> list[Message]:
    return [
        Message(
            id="msg-1",
            chat_id=sample_chat.id,
            role=MessageRole.USER,
            content="What changed?",
            created_at=datetime(2026, 4, 7, 10, 1, tzinfo=UTC),
            metadata=None,
        ),
        Message(
            id="msg-2",
            chat_id=sample_chat.id,
            role=MessageRole.ASSISTANT,
            content="The deployment uses readiness checks.",
            created_at=datetime(2026, 4, 7, 10, 2, tzinfo=UTC),
            metadata={"used_knowledge_files": ["kb-1"]},
        ),
    ]


@pytest.fixture
def sample_processing_result(
    sample_chat: Chat,
    sample_messages: list[Message],
) -> MessageProcessingResult:
    return MessageProcessingResult(
        chat_id=sample_chat.id,
        user_message=sample_messages[0],
        assistant_message=sample_messages[1],
        tool_calls_executed=1,
        used_knowledge_files=["kb-1"],
    )


@pytest.fixture
def sample_events(sample_chat: Chat) -> list[ChatEvent]:
    return [
        ChatEvent(
            id="evt-1",
            chat_id=sample_chat.id,
            event_type=EventType.MESSAGE_RECEIVED,
            payload={"message_id": "msg-1"},
            created_at=datetime(2026, 4, 7, 10, 1, tzinfo=UTC),
        ),
        ChatEvent(
            id="evt-2",
            chat_id=sample_chat.id,
            event_type=EventType.MESSAGE_COMPLETED,
            payload={"assistant_message_id": "msg-2"},
            created_at=datetime(2026, 4, 7, 10, 2, tzinfo=UTC),
        ),
    ]
