from collections.abc import Mapping

import aiosqlite

from app.db.connection import ConnectionFactory, DatabaseError, build_connection_factory


class BaseRepository:
    _entity: str = "row"

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or build_connection_factory()

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
            raise DatabaseError(f"Failed to fetch {self._entity} rows.") from exc
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
            raise DatabaseError(f"Failed to fetch {self._entity} row.") from exc
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
            raise DatabaseError(f"Failed to write {self._entity} row.") from exc
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
            raise DatabaseError(f"Failed to delete {self._entity} row.") from exc
        finally:
            if managed_connection:
                await active_connection.close()
