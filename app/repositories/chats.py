from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite

from app.db.connection import ConnectionFactory, DatabaseError, build_connection_factory


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class ChatsRepository:
    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or build_connection_factory()

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
            "created_at": created_at or _utcnow(),
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
            raise DatabaseError("Failed to fetch chat rows.") from exc
        finally:
            if managed_connection:
                await active_connection.close()

    async def _fetch_one(
        self,
        *,
        query: str,
        parameters: tuple[object, ...],
        connection: aiosqlite.Connection | None,
    ) -> aiosqlite.Row | None:
        managed_connection = connection is None
        active_connection = connection or await self._connection_factory()
        try:
            async with active_connection.execute(query, parameters) as cursor:
                return await cursor.fetchone()
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to fetch chat row.") from exc
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
            raise DatabaseError("Failed to write chat row.") from exc
        finally:
            if managed_connection:
                await active_connection.close()

    async def _execute_delete(
        self,
        *,
        query: str,
        parameters: tuple[object, ...],
        connection: aiosqlite.Connection | None,
    ) -> bool:
        managed_connection = connection is None
        active_connection = connection or await self._connection_factory()
        try:
            cursor = await active_connection.execute(query, parameters)
            await active_connection.commit()
            return cursor.rowcount > 0
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to delete chat row.") from exc
        finally:
            if managed_connection:
                await active_connection.close()
