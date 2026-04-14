from collections.abc import Mapping
from uuid import uuid4

import aiosqlite

from app.repositories.base import BaseRepository
from app.repositories.utils import deserialize_json, serialize_json, utcnow


class MessagesRepository(BaseRepository):
    _entity = "message"

    async def create_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        metadata: Mapping[str, object] | None = None,
        *,
        message_id: str | None = None,
        created_at: str | None = None,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, object | None]:
        message = {
            "id": message_id or str(uuid4()),
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "created_at": created_at or utcnow(),
            "metadata_json": serialize_json(metadata),
        }
        query = """
            INSERT INTO messages (id, chat_id, role, content, created_at, metadata_json)
            VALUES (:id, :chat_id, :role, :content, :created_at, :metadata_json)
        """
        await self._execute_write(query=query, parameters=message, connection=connection)
        return self._row_to_message(message)

    async def list_messages(
        self,
        chat_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        connection: aiosqlite.Connection | None = None,
    ) -> list[dict[str, object | None]]:
        return await self._list_messages(
            chat_id=chat_id,
            ascending=False,
            limit=limit,
            offset=offset,
            connection=connection,
        )

    async def count_messages(
        self,
        chat_id: str,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> int:
        query = "SELECT COUNT(*) FROM messages WHERE chat_id = ?"
        row = await self._fetch_one(query=query, parameters=(chat_id,), connection=connection)
        return int(row[0]) if row is not None else 0

    async def list_messages_ordered(
        self,
        chat_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        connection: aiosqlite.Connection | None = None,
    ) -> list[dict[str, object | None]]:
        return await self._list_messages(
            chat_id=chat_id,
            ascending=True,
            limit=limit,
            offset=offset,
            connection=connection,
        )

    async def _list_messages(
        self,
        *,
        chat_id: str,
        ascending: bool,
        limit: int | None,
        offset: int,
        connection: aiosqlite.Connection | None,
    ) -> list[dict[str, object | None]]:
        direction = "ASC" if ascending else "DESC"
        query = f"""
            SELECT id, chat_id, role, content, created_at, metadata_json
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at {direction}, id {direction}
        """
        parameters: list[object] = [chat_id]
        if limit is not None:
            query += "\nLIMIT ? OFFSET ?"
            parameters.extend([limit, offset])

        rows = await self._fetch_all(
            query=query,
            parameters=tuple(parameters),
            connection=connection,
        )
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _row_to_message(row: Mapping[str, object]) -> dict[str, object | None]:
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
            "metadata": deserialize_json(row["metadata_json"]),
        }
