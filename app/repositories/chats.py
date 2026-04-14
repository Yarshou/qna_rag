from uuid import uuid4

import aiosqlite

from app.repositories.base import BaseRepository
from app.repositories.utils import utcnow


class ChatsRepository(BaseRepository):
    _entity = "chat"

    async def create_chat(
        self,
        *,
        title: str | None = None,
        status: str | None = None,
        chat_id: str | None = None,
        created_at: str | None = None,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, str | None]:
        chat = {
            "id": chat_id or str(uuid4()),
            "created_at": created_at or utcnow(),
            "title": title,
            "status": status,
        }
        query = """
            INSERT INTO chats (id, created_at, title, status)
            VALUES (:id, :created_at, :title, :status)
        """
        await self._execute_write(query=query, parameters=chat, connection=connection)
        return chat

    async def list_chats(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        connection: aiosqlite.Connection | None = None,
    ) -> list[dict[str, str | None]]:
        query = """
            SELECT id, created_at, title, status
            FROM chats
            ORDER BY created_at DESC, id DESC
        """
        parameters: list[int] = []
        if limit is not None:
            query += "\nLIMIT ? OFFSET ?"
            parameters.extend([limit, offset])

        rows = await self._fetch_all(
            query=query,
            parameters=tuple(parameters),
            connection=connection,
        )
        return [dict(row) for row in rows]

    async def count_chats(
        self,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> int:
        query = "SELECT COUNT(*) FROM chats"
        row = await self._fetch_one(query=query, parameters=(), connection=connection)
        return int(row[0]) if row is not None else 0

    async def get_chat(
        self,
        chat_id: str,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, str | None] | None:
        query = """
            SELECT id, created_at, title, status
            FROM chats
            WHERE id = ?
        """
        row = await self._fetch_one(
            query=query,
            parameters=(chat_id,),
            connection=connection,
        )
        return dict(row) if row is not None else None

    async def delete_chat(
        self,
        chat_id: str,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> bool:
        query = "DELETE FROM chats WHERE id = ?"
        return await self._execute_delete(
            query=query,
            parameters=(chat_id,),
            connection=connection,
        )
