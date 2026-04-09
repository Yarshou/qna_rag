from pathlib import Path

import aiosqlite

from app.db.connection import DatabaseError, open_connection

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def load_schema(schema_path: str | Path = SCHEMA_PATH) -> str:
    path = Path(schema_path)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatabaseError(f"Failed to load database schema from '{path}'.") from exc


async def initialize_database(
    *,
    connection: aiosqlite.Connection | None = None,
    db_path: str | Path | None = None,
) -> None:
    schema = load_schema()
    managed_connection = connection is None
    active_connection = connection or await open_connection(db_path=db_path)

    try:
        await active_connection.executescript(schema)
        await active_connection.commit()
    except aiosqlite.Error as exc:
        raise DatabaseError("Failed to initialize SQLite schema.") from exc
    finally:
        if managed_connection:
            await active_connection.close()
