from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config.app import app
from app.domain import Chat, ChatEvent, ChatStatus, EventType, Message, MessageRole
from app.services import ChatNotFoundError, MessageProcessingResult


class FakeChatService:
    def __init__(self, chat: Chat | None) -> None:
        self._chat = chat

    async def create_chat(self, title: str | None = None) -> Chat:
        return replace(self._chat, title=title)

    async def list_chats(self) -> list[Chat]:
        return [] if self._chat is None else [self._chat]

    async def get_chat(self, chat_id: str) -> Chat | None:
        if self._chat is None or self._chat.id != chat_id:
            return None
        return self._chat

    async def delete_chat(self, chat_id: str) -> bool:
        return self._chat is not None and self._chat.id == chat_id


class FakeMessageService:
    def __init__(self, messages: list[Message], processing_result: MessageProcessingResult) -> None:
        self._messages = messages
        self._processing_result = processing_result

    async def list_messages(self, chat_id: str) -> list[Message]:
        if chat_id != self._processing_result.chat_id:
            raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")
        return self._messages

    async def post_user_message(self, chat_id: str, content: str) -> MessageProcessingResult:
        if chat_id != self._processing_result.chat_id:
            raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")
        return self._processing_result


class FakeNotificationService:
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


@pytest.fixture
def client() -> TestClient:
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
def sample_processing_result(sample_chat: Chat, sample_messages: list[Message]) -> MessageProcessingResult:
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


def test_chat_routes(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatService(sample_chat)

    create_response = client.post("/api/v1/chats", json={"title": "  New title  "})
    assert create_response.status_code == 201
    assert create_response.json()["title"] == "New title"

    list_response = client.get("/api/v1/chats")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == sample_chat.id

    delete_response = client.delete(f"/api/v1/chats/{sample_chat.id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": sample_chat.id, "deleted": True}


def test_message_routes(
    client: TestClient,
    sample_chat: Chat,
    sample_processing_result: MessageProcessingResult,
    sample_messages: list[Message],
) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageService(sample_messages, sample_processing_result)

    list_response = client.get(f"/api/v1/chats/{sample_chat.id}/messages")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == ["msg-1", "msg-2"]

    post_response = client.post(
        f"/api/v1/chats/{sample_chat.id}/messages",
        json={"content": "  Tell me more  "},
    )
    assert post_response.status_code == 200
    assert post_response.json()["assistant_message"]["id"] == "msg-2"
    assert post_response.json()["used_knowledge_files"] == ["kb-1"]


def test_event_routes(client: TestClient, sample_chat: Chat, sample_events: list[ChatEvent]) -> None:
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatService(sample_chat)
    app.dependency_overrides[get_notification_service] = lambda: FakeNotificationService(sample_events)

    response = client.get(
        f"/api/v1/chats/{sample_chat.id}/events",
        params={"since": "2026-04-07T10:01:30+00:00", "limit": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "evt-2"


def test_health_routes(client: TestClient) -> None:
    health_response = client.get("/api/v1/healthz")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
