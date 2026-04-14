import asyncio
import logging

from app.domain import Chat
from app.repositories.chats import ChatsRepository

logger = logging.getLogger(__name__)


class ChatService:
    """Application service for chat lifecycle operations."""

    def __init__(self, chats_repository: ChatsRepository | None = None) -> None:
        self._chats_repository = chats_repository or ChatsRepository()

    async def create_chat(self, title: str | None = None) -> Chat:
        logger.info("chat_create_started", extra={"has_title": title is not None})
        chat = Chat.from_mapping(await self._chats_repository.create_chat(title=title))
        logger.info("chat_create_completed", extra={"chat_id": chat.id})
        return chat

    async def list_chats(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Chat], int]:
        chats, total = await asyncio.gather(
            self._chats_repository.list_chats(limit=limit, offset=offset),
            self._chats_repository.count_chats(),
        )
        result = [Chat.from_mapping(chat) for chat in chats]
        logger.info("chat_list_completed", extra={"count": len(result), "total": total})
        return result, total

    async def get_chat(self, chat_id: str) -> Chat | None:
        chat = await self._chats_repository.get_chat(chat_id)
        if chat is None:
            return None
        return Chat.from_mapping(chat)

    async def delete_chat(self, chat_id: str) -> bool:
        deleted = await self._chats_repository.delete_chat(chat_id)
        logger.info("chat_delete_completed", extra={"chat_id": chat_id, "deleted": deleted})
        return deleted
