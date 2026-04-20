"""Startup-time synchronisation between the filesystem KB and SQLite.

This module orchestrates the one-off work required to bring the database in
sync with the on-disk knowledge base; all SQL is delegated to
:class:`~app.repositories.knowledge.KnowledgeRepository`:

* new or modified files are embedded via the provided embeddings client and
  upserted into ``kb_documents`` + ``kb_fts``;
* unchanged files (same ``file_id`` + ``checksum`` + ``embedding_model``)
  are skipped so cold starts after the first run are nearly free;
* files that no longer exist on disk are deleted from both tables.

Embedding API calls are synchronous and executed via
:func:`asyncio.to_thread` to keep the event loop responsive.
"""

import asyncio
import logging

from app.knowledge.loader import KnowledgeLoader
from app.knowledge.models import KnowledgeDocument
from app.repositories.knowledge import KnowledgeRepository

logger = logging.getLogger(__name__)


async def sync_knowledge_index(
    loader: KnowledgeLoader,
    embeddings_client,
    repository: KnowledgeRepository,
    embedding_model: str,
    batch_size: int,
) -> int:
    """Synchronize the on-disk KB with the repository's tables.

    Parameters
    ----------
    loader:
        Filesystem loader used to enumerate documents.
    embeddings_client:
        Any object exposing a synchronous
        ``create_embeddings(list[str]) -> list[list[float]]`` method.
    repository:
        Knowledge repository used for every database access.
    embedding_model:
        Model or deployment name; used to invalidate cache when changed.
    batch_size:
        Number of documents embedded per API call.

    Returns
    -------
    int
        Number of documents present on disk after the sync.
    """

    documents = await asyncio.to_thread(loader.list_documents)
    filesystem_ids = {doc.id for doc in documents}

    existing = await repository.get_cached_metadata()

    docs_to_embed: list[KnowledgeDocument] = []
    reused = 0
    for doc in documents:
        cached = existing.get(doc.id)
        if cached is not None and cached.checksum == doc.checksum and cached.embedding_model == embedding_model:
            reused += 1
        else:
            docs_to_embed.append(doc)

    orphan_ids = list(set(existing) - filesystem_ids)
    if orphan_ids:
        await repository.delete_documents(orphan_ids)
        logger.info(
            "knowledge_index_orphans_removed",
            extra={"count": len(orphan_ids)},
        )

    embedded = 0
    if docs_to_embed:
        embedded = await _embed_and_upsert(
            docs_to_embed,
            embeddings_client,
            repository,
            embedding_model,
            batch_size,
        )

    logger.info(
        "knowledge_index_synced",
        extra={
            "doc_count": len(documents),
            "embedded": embedded,
            "reused": reused,
            "removed": len(orphan_ids),
        },
    )
    return len(documents)


async def _embed_and_upsert(
    docs: list[KnowledgeDocument],
    embeddings_client,
    repository: KnowledgeRepository,
    embedding_model: str,
    batch_size: int,
) -> int:
    """Embed *docs* in batches and persist the results through the repo."""
    total_upserted = 0

    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        try:
            vectors = await asyncio.to_thread(
                embeddings_client.create_embeddings,
                [doc.content for doc in batch],
            )
        except Exception as exc:
            logger.error(
                "knowledge_embedding_batch_failed",
                extra={
                    "error_type": exc.__class__.__name__,
                    "batch_start": start,
                    "batch_size": len(batch),
                },
            )
            continue

        for doc, vec in zip(batch, vectors):
            await repository.upsert_document(
                file_id=doc.id,
                path=doc.path,
                filename=doc.filename,
                checksum=doc.checksum or "",
                embedding=vec,
                embedding_model=embedding_model,
                content=doc.content,
                updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
            )
            total_upserted += 1

    return total_upserted
