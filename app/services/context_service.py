from app.repositories.messages import MessagesRepository
from app.types import Message


class ContextService:
    """Loads persisted message history for chat-oriented workflows."""

    def __init__(self, messages_repository: MessagesRepository | None = None) -> None:
        self._messages_repository = messages_repository or MessagesRepository()

    async def get_chat_history(self, chat_id: str) -> list[Message]:
        messages = await self._messages_repository.list_messages_ordered(chat_id)
        return [Message.from_mapping(message) for message in messages]

    async def get_recent_chat_history(self, chat_id: str, limit: int | None = None) -> list[Message]:
        if limit is None:
            return await self.get_chat_history(chat_id)

        messages = await self._messages_repository.list_messages(chat_id, limit=limit)
        messages.reverse()
        return [Message.from_mapping(message) for message in messages]
