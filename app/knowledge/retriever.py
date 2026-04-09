from app.knowledge.loader import KnowledgeLoader
from app.knowledge.models import KnowledgeDocument, KnowledgeSearchHit, KnowledgeSearchResult
from app.knowledge.ranking import build_snippet, score_document


class KnowledgeRetriever:
    """Provides deterministic file-level retrieval primitives overloaded knowledge documents."""

    def __init__(self, loader: KnowledgeLoader) -> None:
        """Bind the retriever to a knowledge loader instance."""
        self._loader = loader

    def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult:
        """Search candidate files using explicit lexical scoring and return compact ranked hits."""
        normalized_query = query.strip()
        if not normalized_query:
            return KnowledgeSearchResult(query=query, hits=[])

        safe_limit = max(0, limit)
        if safe_limit == 0:
            return KnowledgeSearchResult(query=query, hits=[])

        scored_hits: list[tuple[float, KnowledgeDocument]] = []
        for document in self._loader.list_documents():
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
        """Return full content for a single file selected by its stable knowledge file id."""
        return self._loader.get_document(file_id)
