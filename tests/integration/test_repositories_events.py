"""Integration tests for EventsRepository against a real SQLite database.

These tests exercise the repository through a real on-disk SQLite file
(via ``tmp_path``) so that cursor ordering, chat-scoped lookups and
latest-event retrieval are validated end-to-end, not against in-memory
stubs.
"""

from pathlib import Path

import pytest

from app.db.connection import build_connection_factory
from app.db.init import initialize_database
from app.repositories.chats import ChatsRepository
from app.repositories.events import EventsRepository
from app.shared_types import ChatStatus, EventType


@pytest.mark.anyio
async def test_events_repository_lists_events_after_cursor_in_stable_order(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    connection_factory = build_connection_factory(db_path=db_path)
    chats_repository = ChatsRepository(connection_factory=connection_factory)
    events_repository = EventsRepository(connection_factory=connection_factory)

    await initialize_database(db_path=db_path)
    await chats_repository.create_chat(
        chat_id="chat-1",
        title="Event ordering",
        status=ChatStatus.ACTIVE.value,
        created_at="2026-04-09T10:00:00+00:00",
    )
    await events_repository.create_event(
        chat_id="chat-1",
        event_id="evt-2",
        event_type=EventType.MESSAGE_COMPLETED.value,
        payload={"assistant_message_id": "msg-2"},
        created_at="2026-04-09T10:01:00+00:00",
    )
    await events_repository.create_event(
        chat_id="chat-1",
        event_id="evt-1",
        event_type=EventType.MESSAGE_PROCESSING.value,
        payload={"message_id": "msg-1"},
        created_at="2026-04-09T10:01:00+00:00",
    )
    await events_repository.create_event(
        chat_id="chat-1",
        event_id="evt-3",
        event_type=EventType.MESSAGE_FAILED.value,
        payload={"message_id": "msg-3"},
        created_at="2026-04-09T10:02:00+00:00",
    )

    ordered_events = await events_repository.list_events_after(chat_id="chat-1")
    events_after_cursor = await events_repository.list_events_after(
        chat_id="chat-1",
        after_created_at="2026-04-09T10:01:00+00:00",
        after_id="evt-1",
    )

    assert [event["id"] for event in ordered_events] == ["evt-1", "evt-2", "evt-3"]
    assert [event["id"] for event in events_after_cursor] == ["evt-2", "evt-3"]


@pytest.mark.anyio
async def test_events_repository_returns_chat_scoped_event_by_id(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    connection_factory = build_connection_factory(db_path=db_path)
    chats_repository = ChatsRepository(connection_factory=connection_factory)
    events_repository = EventsRepository(connection_factory=connection_factory)

    await initialize_database(db_path=db_path)
    await chats_repository.create_chat(
        chat_id="chat-1",
        title="Lookup chat",
        status=ChatStatus.ACTIVE.value,
        created_at="2026-04-09T10:00:00+00:00",
    )
    await chats_repository.create_chat(
        chat_id="chat-2",
        title="Other chat",
        status=ChatStatus.ACTIVE.value,
        created_at="2026-04-09T10:05:00+00:00",
    )
    await events_repository.create_event(
        chat_id="chat-1",
        event_id="evt-1",
        event_type=EventType.MESSAGE_RECEIVED.value,
        payload={"message_id": "msg-1"},
        created_at="2026-04-09T10:01:00+00:00",
    )
    await events_repository.create_event(
        chat_id="chat-2",
        event_id="evt-2",
        event_type=EventType.MESSAGE_RECEIVED.value,
        payload={"message_id": "msg-2"},
        created_at="2026-04-09T10:06:00+00:00",
    )

    event = await events_repository.get_event(chat_id="chat-1", event_id="evt-1")
    missing_event = await events_repository.get_event(chat_id="chat-1", event_id="evt-2")
    latest_event = await events_repository.get_latest_event(chat_id="chat-2")

    assert event is not None
    assert event["chat_id"] == "chat-1"
    assert missing_event is None
    assert latest_event is not None
    assert latest_event["id"] == "evt-2"
