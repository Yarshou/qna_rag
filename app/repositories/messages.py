from collections.abc import Mapping
from uuid import uuid4

import aiosqlite

from app.db.connection import ConnectionFactory, DatabaseError, build_connection_factory
from app.repositories.utils import deserialize_json, serialize_json, utcnow


class MessagesRepository:
    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or build_connection_factory()

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

    async def _fetch_all(
        self,
        *,
        query: str,
        parameters: tuple[object, ...],
        connection: aiosqlite.Connection | None,
    ) -> list[aiosqlite.Row]:
        managed_connection = connection is None
        active_connection = connection or await self._connection_factory()
        try:
            async with active_connection.execute(query, parameters) as cursor:
                return await cursor.fetchall()
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to fetch message rows.") from exc
        finally:
            if managed_connection:
                await active_connection.close()

    async def _execute_write(
        self,
        *,
        query: str,
        parameters: Mapping[str, object],
        connection: aiosqlite.Connection | None,
    ) -> None:
        managed_connection = connection is None
        active_connection = connection or await self._connection_factory()
        try:
            await active_connection.execute(query, parameters)
            await active_connection.commit()
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to write message row.") from exc
        finally:
            if managed_connection:
                await active_connection.close()
