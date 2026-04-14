from collections.abc import Mapping
from uuid import uuid4

import aiosqlite

from app.repositories.base import BaseRepository
from app.repositories.utils import deserialize_json, serialize_json, utcnow


class EventsRepository(BaseRepository):
    _entity = "event"

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

    async def list_events_after(
        self,
        chat_id: str,
        *,
        after_created_at: str | None = None,
        after_id: str | None = None,
        limit: int | None = None,
        connection: aiosqlite.Connection | None = None,
    ) -> list[dict[str, object | None]]:
        if (after_created_at is None) != (after_id is None):
            raise ValueError("after_created_at and after_id must be provided together.")

        query = """
            SELECT id, chat_id, event_type, payload_json, created_at
            FROM chat_events
            WHERE chat_id = ?
        """
        parameters: list[object] = [chat_id]

        if after_created_at is not None and after_id is not None:
            query += "\nAND (created_at > ? OR (created_at = ? AND id > ?))"
            parameters.extend([after_created_at, after_created_at, after_id])

        query += "\nORDER BY created_at ASC, id ASC"
        if limit is not None:
            query += "\nLIMIT ?"
            parameters.append(limit)

        rows = await self._fetch_all(
            query=query,
            parameters=tuple(parameters),
            connection=connection,
        )
        return [self._row_to_event(row) for row in rows]

    async def get_event(
        self,
        chat_id: str,
        event_id: str,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, object | None] | None:
        query = """
            SELECT id, chat_id, event_type, payload_json, created_at
            FROM chat_events
            WHERE chat_id = ? AND id = ?
        """
        row = await self._fetch_one(
            query=query,
            parameters=(chat_id, event_id),
            connection=connection,
        )
        return self._row_to_event(row) if row is not None else None

    async def get_latest_event(
        self,
        chat_id: str,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, object | None] | None:
        query = """
            SELECT id, chat_id, event_type, payload_json, created_at
            FROM chat_events
            WHERE chat_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """
        row = await self._fetch_one(
            query=query,
            parameters=(chat_id,),
            connection=connection,
        )
        return self._row_to_event(row) if row is not None else None

    @staticmethod
    def _row_to_event(row: Mapping[str, object]) -> dict[str, object | None]:
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "event_type": row["event_type"],
            "payload": deserialize_json(row["payload_json"]),
            "created_at": row["created_at"],
        }
