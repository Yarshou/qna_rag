import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import events as events_api
from app.config import settings
from app.config.app import app
from app.db.connection import build_connection_factory
from app.db.init import initialize_database
from app.domain import ChatStatus, EventType
from app.repositories.chats import ChatsRepository
from app.repositories.events import EventsRepository
from app.services.notification_service import NotificationService


def _run(coroutine):
    return asyncio.run(coroutine)


def _build_events_repository(db_path: Path) -> EventsRepository:
    return EventsRepository(connection_factory=build_connection_factory(db_path=db_path))


def _build_chats_repository(db_path: Path) -> ChatsRepository:
    return ChatsRepository(connection_factory=build_connection_factory(db_path=db_path))


async def _create_chat(db_path: Path, chat_id: str = "chat-1") -> None:
    await _build_chats_repository(db_path).create_chat(
        chat_id=chat_id,
        title="Streaming chat",
        status=ChatStatus.ACTIVE.value,
        created_at="2026-04-09T10:00:00+00:00",
    )


async def _create_event(
    db_path: Path,
    *,
    chat_id: str,
    event_id: str,
    event_type: str,
    created_at: str,
    payload: dict[str, object] | None = None,
) -> None:
    await _build_events_repository(db_path).create_event(
        chat_id=chat_id,
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        created_at=created_at,
    )


def _notification_service(db_path: Path) -> NotificationService:
    return NotificationService(events_repository=_build_events_repository(db_path))


class StubRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


def _parse_sse_chunk(chunk: str) -> dict[str, str]:
    frame: dict[str, str] = {}
    for line in chunk.strip().splitlines():
        if line.startswith(":"):
            frame["comment"] = line
            continue
        key, value = line.split(": ", 1)
        frame[key] = value
    return frame


@pytest.fixture
def sqlite_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(settings, "DATABASE_PATH", db_path)
    monkeypatch.setattr(events_api, "SSE_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(events_api, "SSE_HEARTBEAT_INTERVAL_SECONDS", 0.05)
    _run(initialize_database(db_path=db_path))
    return db_path


@pytest.fixture
def sqlite_client(sqlite_db_path: Path) -> TestClient:
    with TestClient(app) as client:
        yield client


def test_event_stream_endpoint_returns_not_found_for_unknown_chat(sqlite_client: TestClient) -> None:
    response = sqlite_client.get("/api/v1/chats/chat-2/events/stream")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "chat_not_found",
            "message": "Chat 'chat-2' was not found.",
        }
    }


@pytest.mark.anyio
async def test_event_stream_delivers_persisted_event_without_broker(sqlite_db_path: Path) -> None:
    await _create_chat(sqlite_db_path)
    request = StubRequest()
    notification_service = _notification_service(sqlite_db_path)
    cursor_created_at, cursor_id = await events_api._resolve_stream_cursor(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
    )
    stream = events_api._event_stream(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )

    assert not hasattr(app.state, "event_broker")

    try:
        next_chunk = asyncio.create_task(anext(stream))
        await asyncio.sleep(events_api.SSE_POLL_INTERVAL_SECONDS * 2)
        await notification_service.emit_message_received("chat-1", {"message_id": "msg-1"})
        frame = _parse_sse_chunk(await asyncio.wait_for(next_chunk, timeout=1.0))
    finally:
        request.disconnect()
        await stream.aclose()

    payload = json.loads(frame["data"])
    assert frame["event"] == EventType.MESSAGE_RECEIVED.value
    assert payload["chat_id"] == "chat-1"
    assert payload["payload"] == {"message_id": "msg-1"}


@pytest.mark.anyio
async def test_event_stream_preserves_sqlite_event_order(sqlite_db_path: Path) -> None:
    await _create_chat(sqlite_db_path)
    await _create_event(
        sqlite_db_path,
        chat_id="chat-1",
        event_id="evt-0",
        event_type=EventType.MESSAGE_RECEIVED.value,
        payload={"message_id": "msg-0"},
        created_at="2026-04-09T10:00:00+00:00",
    )
    await _create_event(
        sqlite_db_path,
        chat_id="chat-1",
        event_id="evt-2",
        event_type=EventType.MESSAGE_COMPLETED.value,
        payload={"assistant_message_id": "msg-2"},
        created_at="2026-04-09T10:01:00+00:00",
    )
    await _create_event(
        sqlite_db_path,
        chat_id="chat-1",
        event_id="evt-1",
        event_type=EventType.MESSAGE_PROCESSING.value,
        payload={"message_id": "msg-1"},
        created_at="2026-04-09T10:01:00+00:00",
    )
    request = StubRequest(headers={"last-event-id": "evt-0"})
    notification_service = _notification_service(sqlite_db_path)
    cursor_created_at, cursor_id = await events_api._resolve_stream_cursor(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
    )
    stream = events_api._event_stream(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )

    try:
        first_frame = _parse_sse_chunk(await asyncio.wait_for(anext(stream), timeout=1.0))
        second_frame = _parse_sse_chunk(await asyncio.wait_for(anext(stream), timeout=1.0))
    finally:
        request.disconnect()
        await stream.aclose()

    assert [first_frame["id"], second_frame["id"]] == ["evt-1", "evt-2"]
    assert [first_frame["event"], second_frame["event"]] == [
        EventType.MESSAGE_PROCESSING.value,
        EventType.MESSAGE_COMPLETED.value,
    ]


@pytest.mark.anyio
async def test_event_stream_sends_heartbeat_when_no_new_events(sqlite_db_path: Path) -> None:
    await _create_chat(sqlite_db_path)
    request = StubRequest()
    notification_service = _notification_service(sqlite_db_path)
    cursor_created_at, cursor_id = await events_api._resolve_stream_cursor(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
    )
    stream = events_api._event_stream(
        request=request,
        chat_id="chat-1",
        notification_service=notification_service,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )

    try:
        frame = _parse_sse_chunk(await asyncio.wait_for(anext(stream), timeout=1.0))
    finally:
        request.disconnect()
        await stream.aclose()

    assert frame == {"comment": ": keepalive"}


def test_list_events_endpoint_returns_persisted_events(
    sqlite_client: TestClient,
    sqlite_db_path: Path,
) -> None:
    _run(_create_chat(sqlite_db_path))
    _run(
        _create_event(
            sqlite_db_path,
            chat_id="chat-1",
            event_id="evt-1",
            event_type=EventType.MESSAGE_RECEIVED.value,
            payload={"message_id": "msg-1"},
            created_at="2026-04-09T10:01:00+00:00",
        )
    )
    _run(
        _create_event(
            sqlite_db_path,
            chat_id="chat-1",
            event_id="evt-2",
            event_type=EventType.MESSAGE_COMPLETED.value,
            payload={"assistant_message_id": "msg-2"},
            created_at="2026-04-09T10:02:00+00:00",
        )
    )

    response = sqlite_client.get(
        "/api/v1/chats/chat-1/events",
        params={"since": "2026-04-09T10:01:30+00:00", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "evt-2",
                "chat_id": "chat-1",
                "event_type": "message_completed",
                "payload": {"assistant_message_id": "msg-2"},
                "created_at": "2026-04-09T10:02:00Z",
            }
        ]
    }
