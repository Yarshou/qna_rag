"""Persistence for the knowledge-base index.

Encapsulates every SQL statement that touches ``kb_documents`` and the
``kb_fts`` virtual table, so the knowledge layer above remains a pure
orchestration concern (loader + embeddings + fusion).
"""

import array
from dataclasses import dataclass

import aiosqlite

from app.db.connection import DatabaseError
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class KnowledgeCandidateRow:
    """One candidate returned by :meth:`KnowledgeRepository.load_candidates`."""

    file_id: str
    filename: str
    embedding: list[float]
    content: str


@dataclass(slots=True, frozen=True)
class KnowledgeCacheEntry:
    """Cache metadata used to decide whether a file needs re-embedding."""

    checksum: str
    embedding_model: str


class KnowledgeRepository(BaseRepository):
    """Async repository for the KB index tables.

    Writes (``upsert_document``, ``delete_documents``) keep ``kb_documents``
    and ``kb_fts`` consistent in a single transaction.  Reads
    (``fts_search``, ``load_candidates``, ``list_file_ids``,
    ``get_cached_metadata``) power the stateless hybrid retriever.
    """

    _entity = "kb_document"

    async def get_cached_metadata(
        self,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> dict[str, KnowledgeCacheEntry]:
        """Return ``file_id → {checksum, embedding_model}`` for every row."""
        rows = await self._fetch_all(
            query="SELECT file_id, checksum, embedding_model FROM kb_documents",
            parameters=(),
            connection=connection,
        )
        return {
            row["file_id"]: KnowledgeCacheEntry(
                checksum=row["checksum"],
                embedding_model=row["embedding_model"],
            )
            for row in rows
        }

    async def list_file_ids(
        self,
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> list[str]:
        rows = await self._fetch_all(
            query="SELECT file_id FROM kb_documents",
            parameters=(),
            connection=connection,
        )
        return [row["file_id"] for row in rows]

    async def fts_search(
        self,
        *,
        fts_query: str,
        limit: int,
        connection: aiosqlite.Connection | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``(file_id, bm25_score)`` for the top-N FTS5 matches.

        ``bm25()`` returns non-positive values (lower is better); this method
        flips the sign so callers can fuse the signal as "higher = more
        relevant" alongside cosine similarity.
        """
        managed = connection is None
        conn = connection or await self._connection_factory()
        try:
            async with conn.execute(
                "SELECT file_id, bm25(kb_fts) AS score FROM kb_fts WHERE kb_fts MATCH ? ORDER BY score LIMIT ?",
                (fts_query, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        except aiosqlite.OperationalError:
            # Malformed MATCH expression — treat as "no hits" so the retriever
            # can transparently fall back to semantic-only scoring.
            return []
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to search kb_fts.") from exc
        finally:
            if managed:
                await conn.close()

        return [(row["file_id"], -float(row["score"])) for row in rows]

    async def load_candidates(
        self,
        file_ids: list[str],
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> list[KnowledgeCandidateRow]:
        """Batch-load ``(file_id, filename, embedding, content)`` for *file_ids*."""
        if not file_ids:
            return []

        placeholders = ",".join("?" for _ in file_ids)
        rows = await self._fetch_all(
            query=(
                "SELECT d.file_id, d.filename, d.embedding, f.content "
                "FROM kb_documents AS d "
                "JOIN kb_fts AS f ON f.file_id = d.file_id "
                f"WHERE d.file_id IN ({placeholders})"
            ),
            parameters=tuple(file_ids),
            connection=connection,
        )
        return [
            KnowledgeCandidateRow(
                file_id=row["file_id"],
                filename=row["filename"],
                embedding=_blob_to_vector(row["embedding"]),
                content=row["content"] or "",
            )
            for row in rows
        ]

    async def upsert_document(
        self,
        *,
        file_id: str,
        path: str,
        filename: str,
        checksum: str,
        embedding: list[float],
        embedding_model: str,
        content: str,
        updated_at: str,
        connection: aiosqlite.Connection | None = None,
    ) -> None:
        """Upsert one document's row and refresh its FTS entry atomically."""
        managed = connection is None
        conn = connection or await self._connection_factory()
        try:
            blob = array.array("f", (float(x) for x in embedding)).tobytes()
            await conn.execute(
                """
                INSERT OR REPLACE INTO kb_documents
                    (file_id, path, filename, checksum, embedding,
                     embedding_model, embedding_dim, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    path,
                    filename,
                    checksum,
                    blob,
                    embedding_model,
                    len(embedding),
                    updated_at,
                ),
            )
            # FTS5 lacks UPSERT — delete + insert keeps the row unique.
            await conn.execute("DELETE FROM kb_fts WHERE file_id = ?", (file_id,))
            await conn.execute(
                "INSERT INTO kb_fts (file_id, content) VALUES (?, ?)",
                (file_id, content),
            )
            if managed:
                await conn.commit()
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to upsert kb_document.") from exc
        finally:
            if managed:
                await conn.close()

    async def delete_documents(
        self,
        file_ids: list[str],
        *,
        connection: aiosqlite.Connection | None = None,
    ) -> None:
        """Remove rows from both ``kb_documents`` and ``kb_fts``."""
        if not file_ids:
            return

        managed = connection is None
        conn = connection or await self._connection_factory()
        try:
            params = [(fid,) for fid in file_ids]
            await conn.executemany("DELETE FROM kb_documents WHERE file_id = ?", params)
            await conn.executemany("DELETE FROM kb_fts WHERE file_id = ?", params)
            if managed:
                await conn.commit()
        except aiosqlite.Error as exc:
            raise DatabaseError("Failed to delete kb_documents.") from exc
        finally:
            if managed:
                await conn.close()


def _blob_to_vector(blob: bytes) -> list[float]:
    arr = array.array("f")
    arr.frombytes(blob)
    return list(arr)
