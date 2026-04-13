"""Non-happy path tests for all API endpoints.

Covers 404, 422, 500, and 502 error scenarios without touching real
infrastructure — all service dependencies are replaced with fakes that
raise or return the values needed to exercise each error branch.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config.app import app
from app.domain import Chat, ChatEvent, ChatStatus, Message
from app.llm.exceptions import LLMClientConfigurationError, LLMProviderError
from app.services import ChatNotFoundError, MessageProcessingError
from app.services.message_service import MessageProcessingResult


class _FakeChatServiceMissing:
    """Always reports chats as absent; causes 404 on delete."""

    async def create_chat(self, title: str | None = None) -> Chat:
        return Chat(
            id="new-chat",
            title=title,
            status=ChatStatus.ACTIVE,
            created_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
        )

    async def list_chats(self) -> list[Chat]:
        return []

    async def get_chat(self, chat_id: str) -> Chat | None:
        return None

    async def delete_chat(self, chat_id: str) -> bool:
        return False


class _FakeChatServiceBroken:
    """Raises on every mutating or listing call; exercises 500 branches."""

    async def create_chat(self, title: str | None = None) -> Chat:
        raise RuntimeError("DB connection failed")

    async def list_chats(self) -> list[Chat]:
        raise RuntimeError("DB connection failed")

    async def get_chat(self, chat_id: str) -> Chat | None:
        return None

    async def delete_chat(self, chat_id: str) -> bool:
        raise RuntimeError("DB connection failed")


class _FakeMessageServiceRaises:
    """Raises a caller-supplied exception from post_user_message."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def list_messages(self, chat_id: str) -> list[Message]:
        raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")

    async def post_user_message(self, chat_id: str, content: str) -> MessageProcessingResult:
        raise self._error


class _FakeNotificationServiceEmpty:
    """Returns empty event lists; used to allow list_events to succeed."""

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
def client() -> TestClient:
    with TestClient(app) as test_client:
        app.dependency_overrides.clear()
        yield test_client
        app.dependency_overrides.clear()


@pytest.fixture
def sample_chat() -> Chat:
    return Chat(
        id="chat-1",
        title="Test chat",
        status=ChatStatus.ACTIVE,
        created_at=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
    )


def test_delete_nonexistent_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceMissing()

    response = client.delete("/api/v1/chats/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "chat_not_found"
    assert "does-not-exist" in body["error"]["message"]


def test_create_chat_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceBroken()

    response = client.post("/api/v1/chats", json={})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_list_chats_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceBroken()

    response = client.get("/api/v1/chats")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_delete_chat_internal_error_returns_500(client: TestClient) -> None:
    from app.api.v1.chats import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceBroken()

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

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        ChatNotFoundError("Chat 'unknown' was not found.")
    )

    response = client.get("/api/v1/chats/unknown/messages")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_post_message_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        ChatNotFoundError("Chat 'unknown' was not found.")
    )

    response = client.post("/api/v1/chats/unknown/messages", json={"content": "Hello"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_post_message_provider_error_returns_502(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        LLMProviderError("The provider timed out.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


def test_post_message_configuration_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        LLMClientConfigurationError("AZURE_OPENAI_API_KEY is required.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "configuration_error"


def test_post_message_processing_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        MessageProcessingError("Assistant exceeded tool-calling rounds.")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "message_processing_failed"


def test_post_message_unexpected_error_returns_500(client: TestClient, sample_chat: Chat) -> None:
    from app.api.v1.messages import get_message_service

    app.dependency_overrides[get_message_service] = lambda: _FakeMessageServiceRaises(
        RuntimeError("Something completely unexpected")
    )

    response = client.post(f"/api/v1/chats/{sample_chat.id}/messages", json={"content": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_list_events_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: _FakeNotificationServiceEmpty()

    response = client.get("/api/v1/chats/ghost-chat/events")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_stream_events_unknown_chat_returns_404(client: TestClient) -> None:
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: _FakeNotificationServiceEmpty()

    response = client.get("/api/v1/chats/ghost-chat/events/stream")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_not_found"


def test_list_events_with_limit_zero_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """The limit query parameter has ge=1 — zero must be rejected."""
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: _FakeNotificationServiceEmpty()

    response = client.get(f"/api/v1/chats/{sample_chat.id}/events", params={"limit": 0})

    assert response.status_code == 422


def test_list_events_with_invalid_since_returns_422(client: TestClient, sample_chat: Chat) -> None:
    """Passing a non-datetime string for 'since' must be rejected by FastAPI."""
    from app.api.v1.events import get_chat_service, get_notification_service

    app.dependency_overrides[get_chat_service] = lambda: _FakeChatServiceMissing()
    app.dependency_overrides[get_notification_service] = lambda: _FakeNotificationServiceEmpty()

    response = client.get(
        f"/api/v1/chats/{sample_chat.id}/events",
        params={"since": "not-a-date"},
    )

    assert response.status_code == 422
