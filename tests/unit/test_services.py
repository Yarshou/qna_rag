"""Unit tests for ChatService, ContextService, and NotificationService.

All tests use in-memory fake repositories so no database or external I/O
is required.  Each fake implements only the repository methods that the
corresponding service actually calls, keeping the fakes minimal and the
tests focused.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.shared_types import Chat, ChatEvent, Message
from app.shared_types.enums import ChatStatus, EventType, MessageRole
from app.services.chat_service import ChatService
from app.services.context_service import ContextService
from app.services.notification_service import NotificationService

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _chat_row(chat_id: str, title: str | None = None) -> dict[str, Any]:
    return {
        "id": chat_id,
        "title": title,
        "status": ChatStatus.ACTIVE.value,
        "created_at": _NOW.isoformat(),
    }


def _message_row(message_id: str, chat_id: str, role: str = "user", content: str = "hi") -> dict[str, Any]:
    return {
        "id": message_id,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "created_at": _NOW.isoformat(),
        "metadata": None,
    }


def _event_row(event_id: str, chat_id: str, event_type: str = "message_received") -> dict[str, Any]:
    return {
        "id": event_id,
        "chat_id": chat_id,
        "event_type": event_type,
        "payload": None,
        "created_at": _NOW.isoformat(),
    }


class FakeChatsRepository:
    def __init__(self, chats: list[dict[str, Any]] | None = None) -> None:
        self._chats: dict[str, dict[str, Any]] = {c["id"]: c for c in (chats or [])}

    async def create_chat(self, *, title: str | None = None) -> dict[str, Any]:
        chat_id = str(uuid.uuid4())
        row = _chat_row(chat_id, title)
        self._chats[chat_id] = row
        return row

    async def list_chats(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return list(self._chats.values())[offset : offset + limit]

    async def count_chats(self) -> int:
        return len(self._chats)

    async def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        return self._chats.get(chat_id)

    async def delete_chat(self, chat_id: str) -> bool:
        if chat_id in self._chats:
            del self._chats[chat_id]
            return True
        return False


class FakeMessagesRepository:
    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self._messages: list[dict[str, Any]] = messages or []

    async def list_messages_ordered(self, chat_id: str) -> list[dict[str, Any]]:
        return [m for m in self._messages if m["chat_id"] == chat_id]

    async def list_messages(self, chat_id: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = [m for m in self._messages if m["chat_id"] == chat_id]
        return rows[offset : offset + limit]


class FakeEventsRepository:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events: list[dict[str, Any]] = events or []

    async def create_event(
        self,
        *,
        chat_id: str,
        event_type: str,
        payload: Any = None,
    ) -> dict[str, Any]:
        row = _event_row(str(uuid.uuid4()), chat_id, event_type)
        row["payload"] = dict(payload) if payload is not None else None
        self._events.append(row)
        return row

    async def list_events(
        self,
        *,
        chat_id: str,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = [e for e in self._events if e["chat_id"] == chat_id]
        return rows[:limit] if limit is not None else rows

    async def list_events_after(
        self,
        *,
        chat_id: str,
        after_created_at: str | None = None,
        after_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = [e for e in self._events if e["chat_id"] == chat_id]
        return rows[:limit] if limit is not None else rows

    async def get_event(self, *, chat_id: str, event_id: str) -> dict[str, Any] | None:
        return next((e for e in self._events if e["id"] == event_id and e["chat_id"] == chat_id), None)

    async def get_latest_event(self, *, chat_id: str) -> dict[str, Any] | None:
        rows = [e for e in self._events if e["chat_id"] == chat_id]
        return rows[-1] if rows else None


@pytest.mark.anyio
async def test_chat_service_create_returns_chat() -> None:
    service = ChatService(FakeChatsRepository())

    chat = await service.create_chat(title="Test")

    assert isinstance(chat, Chat)
    assert chat.title == "Test"
    assert chat.status == ChatStatus.ACTIVE


@pytest.mark.anyio
async def test_chat_service_create_without_title() -> None:
    service = ChatService(FakeChatsRepository())

    chat = await service.create_chat()

    assert chat.title is None


@pytest.mark.anyio
async def test_chat_service_get_returns_none_for_missing_chat() -> None:
    service = ChatService(FakeChatsRepository())

    result = await service.get_chat("nonexistent")

    assert result is None


@pytest.mark.anyio
async def test_chat_service_get_returns_existing_chat() -> None:
    repo = FakeChatsRepository([_chat_row("chat-1", "Hello")])
    service = ChatService(repo)

    chat = await service.get_chat("chat-1")

    assert chat is not None
    assert chat.id == "chat-1"
    assert chat.title == "Hello"


@pytest.mark.anyio
async def test_chat_service_list_returns_all_chats_with_total() -> None:
    repo = FakeChatsRepository([_chat_row("c1"), _chat_row("c2"), _chat_row("c3")])
    service = ChatService(repo)

    chats, total = await service.list_chats()

    assert len(chats) == 3
    assert total == 3
    assert all(isinstance(c, Chat) for c in chats)


@pytest.mark.anyio
async def test_chat_service_list_respects_limit_and_offset() -> None:
    repo = FakeChatsRepository([_chat_row(f"c{i}") for i in range(5)])
    service = ChatService(repo)

    chats, total = await service.list_chats(limit=2, offset=1)

    assert len(chats) == 2
    assert total == 5


@pytest.mark.anyio
async def test_chat_service_delete_existing_chat_returns_true() -> None:
    repo = FakeChatsRepository([_chat_row("chat-1")])
    service = ChatService(repo)

    deleted = await service.delete_chat("chat-1")

    assert deleted is True
    assert await service.get_chat("chat-1") is None


@pytest.mark.anyio
async def test_chat_service_delete_missing_chat_returns_false() -> None:
    service = ChatService(FakeChatsRepository())

    deleted = await service.delete_chat("ghost")

    assert deleted is False


@pytest.mark.anyio
async def test_context_service_returns_empty_history_for_new_chat() -> None:
    service = ContextService(FakeMessagesRepository())

    history = await service.get_chat_history("chat-1")

    assert history == []


@pytest.mark.anyio
async def test_context_service_returns_messages_as_domain_objects() -> None:
    rows = [
        _message_row("m1", "chat-1", role="user", content="Hello"),
        _message_row("m2", "chat-1", role="assistant", content="Hi"),
    ]
    service = ContextService(FakeMessagesRepository(rows))

    history = await service.get_chat_history("chat-1")

    assert len(history) == 2
    assert all(isinstance(m, Message) for m in history)
    assert history[0].role == MessageRole.USER
    assert history[1].role == MessageRole.ASSISTANT


@pytest.mark.anyio
async def test_context_service_filters_by_chat_id() -> None:
    rows = [
        _message_row("m1", "chat-1", content="Chat 1 message"),
        _message_row("m2", "chat-2", content="Chat 2 message"),
    ]
    service = ContextService(FakeMessagesRepository(rows))

    history = await service.get_chat_history("chat-1")

    assert len(history) == 1
    assert history[0].content == "Chat 1 message"


@pytest.mark.anyio
async def test_context_service_recent_history_without_limit_returns_all() -> None:
    rows = [_message_row(f"m{i}", "chat-1") for i in range(5)]
    service = ContextService(FakeMessagesRepository(rows))

    history = await service.get_recent_chat_history("chat-1")

    assert len(history) == 5


@pytest.mark.anyio
async def test_context_service_recent_history_with_limit_truncates() -> None:
    rows = [_message_row(f"m{i}", "chat-1") for i in range(5)]
    service = ContextService(FakeMessagesRepository(rows))

    history = await service.get_recent_chat_history("chat-1", limit=2)

    assert len(history) == 2


@pytest.mark.anyio
async def test_notification_service_disabled_emit_returns_none() -> None:
    service = NotificationService(enabled=False)

    result = await service.emit_message_received("chat-1")

    assert result is None


@pytest.mark.anyio
async def test_notification_service_disabled_list_returns_empty() -> None:
    service = NotificationService(enabled=False)

    events = await service.list_events("chat-1")

    assert events == []


@pytest.mark.anyio
async def test_notification_service_emit_persists_event() -> None:
    repo = FakeEventsRepository()
    service = NotificationService(repo)

    event = await service.emit_message_received("chat-1", payload={"key": "value"})

    assert event is not None
    assert isinstance(event, ChatEvent)
    assert event.chat_id == "chat-1"
    assert event.event_type == EventType.MESSAGE_RECEIVED


@pytest.mark.anyio
async def test_notification_service_all_emit_methods_produce_correct_types() -> None:
    repo = FakeEventsRepository()
    service = NotificationService(repo)

    cases = [
        (service.emit_message_received, EventType.MESSAGE_RECEIVED),
        (service.emit_message_processing, EventType.MESSAGE_PROCESSING),
        (service.emit_tool_called, EventType.TOOL_CALLED),
        (service.emit_message_completed, EventType.MESSAGE_COMPLETED),
        (service.emit_message_failed, EventType.MESSAGE_FAILED),
    ]

    for method, expected_type in cases:
        event = await method("chat-1")
        assert event is not None
        assert event.event_type == expected_type, f"Expected {expected_type}, got {event.event_type}"


@pytest.mark.anyio
async def test_notification_service_list_events_returns_domain_objects() -> None:
    event_row = _event_row("evt-1", "chat-1", EventType.MESSAGE_RECEIVED.value)
    repo = FakeEventsRepository([event_row])
    service = NotificationService(repo)

    events = await service.list_events("chat-1")

    assert len(events) == 1
    assert isinstance(events[0], ChatEvent)
    assert events[0].id == "evt-1"


@pytest.mark.anyio
async def test_notification_service_list_events_after_returns_domain_objects() -> None:
    rows = [_event_row(f"evt-{i}", "chat-1") for i in range(3)]
    repo = FakeEventsRepository(rows)
    service = NotificationService(repo)

    events = await service.list_events_after("chat-1", limit=2)

    assert len(events) == 2
    assert all(isinstance(e, ChatEvent) for e in events)


@pytest.mark.anyio
async def test_notification_service_get_event_returns_correct_event() -> None:
    row = _event_row("evt-42", "chat-1")
    repo = FakeEventsRepository([row])
    service = NotificationService(repo)

    event = await service.get_event("chat-1", "evt-42")

    assert event is not None
    assert event.id == "evt-42"


@pytest.mark.anyio
async def test_notification_service_get_event_returns_none_for_missing_id() -> None:
    service = NotificationService(FakeEventsRepository())

    result = await service.get_event("chat-1", "ghost")

    assert result is None


@pytest.mark.anyio
async def test_notification_service_get_latest_event_returns_last_emitted() -> None:
    repo = FakeEventsRepository()
    service = NotificationService(repo)

    await service.emit_message_received("chat-1")
    await service.emit_message_processing("chat-1")
    latest = await service.get_latest_event("chat-1")

    assert latest is not None
    assert latest.event_type == EventType.MESSAGE_PROCESSING


@pytest.mark.anyio
async def test_notification_service_get_latest_event_returns_none_for_empty_chat() -> None:
    service = NotificationService(FakeEventsRepository())

    result = await service.get_latest_event("chat-1")

    assert result is None
