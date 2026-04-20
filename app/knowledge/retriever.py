"""Stateless hybrid retrieval over the ``kb_documents`` / ``kb_fts`` tables.

For every call the retriever:

1. embeds the query via the configured embeddings client;
2. asks the repository for the top-N BM25 candidates (FTS5);
3. loads those candidates' persisted embeddings + content;
4. computes cosine similarity with NumPy;
5. fuses the two signals with min-max normalisation and a weighted sum.

All SQL access is delegated to
:class:`~app.repositories.knowledge.KnowledgeRepository`; the retriever
itself keeps no per-document state.
"""

import logging

from app.knowledge.loader import KnowledgeLoader
from app.knowledge.models import (
    KnowledgeDocument,
    KnowledgeSearchHit,
    KnowledgeSearchResult,
)
from app.knowledge.ranking import (
    build_snippet_from_content,
    cosine_scores,
    min_max_normalize,
    tokenize,
)
from app.repositories.knowledge import KnowledgeRepository

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """SQLite-backed hybrid retriever (FTS5 BM25 + cosine on embeddings).

    Parameters
    ----------
    repository:
        :class:`~app.repositories.knowledge.KnowledgeRepository` used for
        every database access.
    embeddings_client:
        Duck-typed: must expose
        ``create_embeddings(list[str]) -> list[list[float]]``.
    loader:
        Filesystem loader used only by :meth:`read_knowledge_file`.
    hybrid_lexical_weight:
        ``α ∈ [0, 1]`` — weight of the BM25 signal in the fused score.
    fts_candidate_limit:
        Maximum number of BM25 candidates to pull before semantic re-ranking.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        embeddings_client,
        loader: KnowledgeLoader,
        hybrid_lexical_weight: float = 0.5,
        fts_candidate_limit: int = 20,
    ) -> None:
        self._repository = repository
        self._embeddings_client = embeddings_client
        self._loader = loader
        self._alpha = max(0.0, min(1.0, hybrid_lexical_weight))
        self._fts_candidate_limit = max(1, fts_candidate_limit)

    async def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult:
        """Return ranked hits for *query* (file-level)."""
        normalized_query = query.strip()
        safe_limit = max(0, limit)
        if not normalized_query or safe_limit == 0:
            return KnowledgeSearchResult(query=query, hits=[])

        fts_tokens = tokenize(normalized_query)
        fts_query = " ".join(fts_tokens)

        lex_by_id: dict[str, float] = {}
        if fts_query:
            fts_hits = await self._repository.fts_search(
                fts_query=fts_query,
                limit=self._fts_candidate_limit,
            )
            lex_by_id = dict(fts_hits)

        if lex_by_id:
            candidate_ids = list(lex_by_id.keys())
        else:
            # FTS5 yielded nothing (no usable tokens or no matches) — fall back
            # to cosine-only scoring over every indexed document.
            candidate_ids = await self._repository.list_file_ids()

        if not candidate_ids:
            return KnowledgeSearchResult(query=query, hits=[])

        candidates = await self._repository.load_candidates(candidate_ids)
        if not candidates:
            return KnowledgeSearchResult(query=query, hits=[])

        query_vec = self._embed_query(normalized_query)

        doc_vecs = [row.embedding for row in candidates]
        if query_vec is not None and doc_vecs:
            sem_list = cosine_scores(query_vec, doc_vecs)
        else:
            sem_list = [0.0] * len(candidates)

        lex_list = [lex_by_id.get(row.file_id, 0.0) for row in candidates]

        norm_lex = min_max_normalize(lex_list)
        norm_sem = min_max_normalize(sem_list)

        alpha = self._alpha
        scored = [
            (
                alpha * norm_lex[i] + (1.0 - alpha) * norm_sem[i],
                lex_list[i],
                sem_list[i],
                candidates[i],
            )
            for i in range(len(candidates))
        ]
        scored.sort(key=lambda item: (-item[0], item[3].filename, item[3].file_id))

        hits = [
            KnowledgeSearchHit(
                file_id=row.file_id,
                filename=row.filename,
                score=round(fused, 4),
                snippet=build_snippet_from_content(row.content, normalized_query) or None,
                lexical_score=round(lex, 4),
                semantic_score=round(sem, 4),
            )
            for fused, lex, sem, row in scored[:safe_limit]
        ]

        logger.info(
            "knowledge_retrieval_scored",
            extra={
                "candidates": len(candidates),
                "hits": len(hits),
                "alpha": alpha,
                "fts_used": bool(lex_by_id),
            },
        )
        return KnowledgeSearchResult(query=query, hits=hits)

    async def read_knowledge_file(self, file_id: str) -> KnowledgeDocument | None:
        """Return the full content of a single file by its stable ID."""
        return self._loader.get_document(file_id)

    # ── private helpers ──────────────────────────────────────────────────────

    def _embed_query(self, query: str) -> list[float] | None:
        if self._embeddings_client is None:
            return None
        try:
            vectors = self._embeddings_client.create_embeddings([query])
        except Exception as exc:
            logger.warning(
                "knowledge_query_embedding_failed",
                extra={"error_type": exc.__class__.__name__},
            )
            return None
        return vectors[0] if vectors else None
