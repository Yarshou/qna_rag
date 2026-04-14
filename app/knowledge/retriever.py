"""Knowledge base retrieval primitives backed by any DocumentStoreProtocol.

The retriever is intentionally decoupled from the storage layer via
:class:`DocumentStoreProtocol`.  This allows both
:class:`~app.knowledge.loader.KnowledgeLoader` (direct filesystem reads) and
:class:`~app.knowledge.indexer.KnowledgeIndexer` (in-memory cache) to be
used interchangeably as the backing store.

In production the indexer is preferred because it eliminates per-query
filesystem scans.  In tests or development the loader can be passed directly
without building an index first.
"""

from typing import Protocol

from app.knowledge.models import KnowledgeDocument, KnowledgeSearchHit, KnowledgeSearchResult
from app.knowledge.ranking import build_snippet, score_document


class DocumentStoreProtocol(Protocol):
    """Minimal interface required by :class:`KnowledgeRetriever`.

    Both :class:`~app.knowledge.loader.KnowledgeLoader` and
    :class:`~app.knowledge.indexer.KnowledgeIndexer` satisfy this protocol
    structurally — no explicit inheritance is required.
    """

    def list_documents(self) -> list[KnowledgeDocument]:
        """Return all available knowledge documents."""
        ...

    def get_document(self, file_id: str) -> KnowledgeDocument | None:
        """Return a single document by its stable file ID, or ``None``."""
        ...


class KnowledgeRetriever:
    """Provides deterministic file-level retrieval over a document store.

    Accepts any object that satisfies :class:`DocumentStoreProtocol` — pass a
    :class:`~app.knowledge.indexer.KnowledgeIndexer` for production use (no
    per-query I/O) or a :class:`~app.knowledge.loader.KnowledgeLoader` for
    lightweight scripts and tests.
    """

    def __init__(self, store: DocumentStoreProtocol) -> None:
        """Bind the retriever to a document store.

        Parameters
        ----------
        store:
            Any object that satisfies :class:`DocumentStoreProtocol`.
        """
        self._store = store

    def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult:
        """Search candidate files using lexical scoring and return ranked hits.

        Documents are scored with :func:`~app.knowledge.ranking.score_document`
        and sorted by ``(score DESC, filename ASC, id ASC)`` for stable
        ordering.  Zero-score documents are excluded from results.

        Parameters
        ----------
        query:
            Raw user query string; whitespace is normalised internally.
        limit:
            Maximum number of results to return.  Values ``≤ 0`` return an
            empty result.

        Returns
        -------
        KnowledgeSearchResult
            Ranked search hits with optional snippets.
        """
        normalized_query = query.strip()
        if not normalized_query:
            return KnowledgeSearchResult(query=query, hits=[])

        safe_limit = max(0, limit)
        if safe_limit == 0:
            return KnowledgeSearchResult(query=query, hits=[])

        scored_hits: list[tuple[float, KnowledgeDocument]] = []
        for document in self._store.list_documents():
            score = score_document(document, normalized_query)
            if score <= 0:
                continue
            scored_hits.append((score, document))

        scored_hits.sort(key=lambda item: (-item[0], item[1].filename, item[1].id))
        hits = [
            KnowledgeSearchHit(
                file_id=document.id,
                filename=document.filename,
                score=round(score, 4),
                snippet=build_snippet(document, normalized_query) or None,
            )
            for score, document in scored_hits[:safe_limit]
        ]

        return KnowledgeSearchResult(query=query, hits=hits)

    def read_knowledge_file(self, file_id: str) -> KnowledgeDocument | None:
        """Return the full content of a single file by its stable knowledge file ID.

        Parameters
        ----------
        file_id:
            Stable SHA-256-derived identifier assigned at index time.

        Returns
        -------
        KnowledgeDocument | None
            The document with full content, or ``None`` if not found.
        """
        return self._store.get_document(file_id)
