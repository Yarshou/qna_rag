from collections.abc import Awaitable, Callable
from pathlib import Path

import aiosqlite

from app.config import settings
from app.db.exceptions import DatabaseConfigurationError, DatabaseError

ConnectionFactory = Callable[[], Awaitable[aiosqlite.Connection]]


def resolve_database_path(db_path: str | Path | None = None) -> Path:
    path_value = db_path or settings.DATABASE_PATH
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (settings.BASE_DIR.parent / path).resolve()
    return path


async def open_connection(db_path: str | Path | None = None) -> aiosqlite.Connection:
    database_path = resolve_database_path(db_path)
    if not database_path.name:
        raise DatabaseConfigurationError("Database path must point to a SQLite file.")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        connection = await aiosqlite.connect(database_path.as_posix())
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON;")
        await connection.execute("PRAGMA busy_timeout = 5000;")
        return connection
    except aiosqlite.Error as exc:
        raise DatabaseError(f"Failed to open SQLite connection at '{database_path}'.") from exc


def build_connection_factory(db_path: str | Path | None = None) -> ConnectionFactory:
    async def _factory() -> aiosqlite.Connection:
        return await open_connection(db_path=db_path)

    return _factory
