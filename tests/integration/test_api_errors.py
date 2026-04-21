"""Non-happy path tests for all API endpoints.

Covers 404, 422, 500, and 502 error scenarios without touching real
infrastructure — all service dependencies are replaced with fakes from
``conftest.py`` that raise or return the values needed to exercise each
error branch.
"""

from fastapi.testclient import TestClient

from app.config.app import app
from app.llm.exceptions import LLMClientConfigurationError, LLMProviderError
from app.services import ChatNotFoundError, MessageProcessingError
from app.shared_types import Chat
from tests.integration.conftest import (
    FakeChatServiceBroken,
    FakeChatServiceMissing,
    FakeMessageServiceRaises,
    FakeNotificationServiceEmpty,
)


def test_delete_nonexistent_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceMissing()

    response = client.delete("/api/v1/chats/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "chat_not_found"
    assert "does-not-exist" in body["error"]["message"]


def test_create_chat_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceBroken()

    response = client.post("/api/v1/chats", json={})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_list_chats_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceBroken()

    response = client.get("/api/v1/chats")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_delete_chat_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceBroken()

    response = client.delete("/api/v1/chats/chat-1")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_post_message_missing_content_returns_422(client: TestClient, sample_chat: Chat) -> None:
    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={})

    assert response.status_code == 422


def test_post_message_empty_content_returns_422(client: TestClient, sample_chat: Chat) -> None:
    response = client.post(
        f"/api/v1/chats/{sample_chat.id}/messages",
        json={"content": ""},
    )

    assert response.status_code == 422


def test_post_message_whitespace_only_content_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """The content validator strips whitespace; bare spaces must also be rejected."""
    response = client.post(
        f"/api/v1/chats/{sample_chat.id}/messages",
        json={"content": "   "},
    )

    assert response.status_code == 422


def test_post_message_extra_field_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """PostMessageRequest uses extra='forbid', so unknown fields must fail."""
    response = client.post(
        f"/api/v1/chats/{sample_chat.id}/messages",
        json={"content": "Hello", "unexpected_key": "value"},
    )

    assert response.status_code == 422


def test_post_message_non_string_content_returns_422(client: TestClient, sample_chat: Chat) -> None:
    response = client.post(
        f"/api/v1/chats/{sample_chat.id}/messages",
        json={"content": 42},
    )

    assert response.status_code == 422


def test_list_messages_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        ChatNotFoundError("Chat 'unknown' was not found.")
    )

    response = client.get("/api/v1/chats/unknown/messages")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_post_message_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        ChatNotFoundError("Chat 'unknown' was not found.")
    )

    response = client.post("/api/v1/chats/unknown/messages", json={"content": "Hello"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_post_message_provider_error_returns_502(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        LLMProviderError("The provider timed out.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


def test_post_message_configuration_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        LLMClientConfigurationError("AZURE_OPENAI_API_KEY is required.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "configuration_error"


def test_post_message_processing_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        MessageProcessingError("Assistant exceeded tool-calling rounds.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "message_processing_failed"


def test_post_message_unexpected_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: FakeMessageServiceRaises(
        RuntimeError("Something completely unexpected")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_list_events_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: FakeNotificationServiceEmpty()

    response = client.get("/api/v1/chats/ghost-chat/events")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_stream_events_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: FakeNotificationServiceEmpty()

    response = client.get("/api/v1/chats/ghost-chat/events/stream")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_list_events_with_limit_zero_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """The limit query parameter has ge=1 — zero must be rejected."""
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: FakeNotificationServiceEmpty()

    response = client.get(f"/api/v1/chats/{sample_chat.id}/events", params={"limit": 0})

    assert response.status_code == 422


def test_list_events_with_invalid_since_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """Passing a non-datetime string for 'since' must be rejected by FastAPI."""
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: FakeNotificationServiceEmpty()

    response = client.get(
        f"/api/v1/chats/{sample_chat.id}/events",
        params={"since": "not-a-date"},
    )

    assert response.status_code == 422
