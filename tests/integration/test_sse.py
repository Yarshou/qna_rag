from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config.app import app
from app.domain import Chat, ChatStatus


class FakeChatService:
    def __init__(self, chat: Chat | None) -> None:
        self._chat = chat

    async def get_chat(self, chat_id: str) -> Chat | None:
        if self._chat is None or self._chat.id != chat_id:
            return None
        return self._chat


def test_event_stream_endpoint_returns_not_found_for_unknown_chat() -> None:
    from app.api.v1.events import get_chat_service

    chat = Chat(
        id="chat-1",
        title="Streaming chat",
        status=ChatStatus.ACTIVE,
        created_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
    )
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService(chat)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/chats/chat-2/events/stream")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "chat_not_found",
            "message": "Chat 'chat-2' was not found.",
        }
    }
