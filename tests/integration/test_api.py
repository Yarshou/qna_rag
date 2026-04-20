"""Happy-path API integration tests.

These tests hit the FastAPI application through ``TestClient`` with
business-logic services replaced by fakes from ``conftest.py``, so only
the HTTP stack (routing, schemas, status codes, serialisation) is
exercised.
"""

from fastapi.testclient import TestClient

from app.common_types import Chat, ChatEvent, Message
from app.config.app import app
from app.services import MessageProcessingResult
from tests.integration.conftest import (
    FakeChatService,
    FakeMessageService,
    FakeNotificationService,
)


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
    assert delete_response.status_code == 204
    assert delete_response.content == b""


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
    assert post_response.status_code == 201
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
