from collections.abc import Mapping
from uuid import uuid4

import aiosqlite

from app.db.connection import ConnectionFactory, DatabaseError, build_connection_factory
from app.repositories.utils import deserialize_json, serialize_json, utcnow


class EventsRepository:
    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or build_connection_factory()

    async def create_event(
        self,
        chat_id: str,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        *,
        event_id: str | None = None,
        created_at: str | None = None,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, object | None]:
        event = {
            "id": event_id or str(uuid4()),
            "chat_id": chat_id,
            "event_type": event_type,
            "payload_json": serialize_json(payload),
            "created_at": created_at or utcnow(),
        }
        query = """
            INSERT INTO chat_events (id, chat_id, event_type, payload_json, created_at)
            VALUES (:id, :chat_id, :event_type, :payload_json, :created_at)
        """
        await self._execute_write(query=query, parameters=event, connection=connection)
        return self._row_to_event(event)

    async def list_events(
        self,
        chat_id: str,
        *,
        since: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        connection: aiosqlite.Connection | None = None,
    ) -> list[dict[str, object | None]]:
        query = """
            SELECT id, chat_id, event_type, payload_json, created_at
            FROM chat_events
            WHERE chat_id = ?
        """
        parameters: list[object] = [chat_id]

        if since is not None:
            query += "\nAND created_at >= ?"
            parameters.append(since)

        query += "\nORDER BY created_at ASC, id ASC"
        if limit is not None:
            query += "\nLIMIT ? OFFSET ?"
            parameters.extend([limit, offset])

        rows = await self._fetch_all(
            query=query,
            parameters=tuple(parameters),
            connection=connection,
        )
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: Mapping[str, object]) -> dict[str, object | None]:
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "event_type": row["event_type"],
            "payload": deserialize_json(row["payload_json"]),
            "created_at": row["created_at"],
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
            raise DatabaseError("Failed to fetch event rows.") from exc
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
            raise DatabaseError("Failed to write event row.") from exc
        finally:
            if managed_connection:
                await active_connection.close()
