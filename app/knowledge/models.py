from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class KnowledgeDocument:
    """Represents one text file loaded from the knowledge base."""

    id: str
    filename: str
    path: str
    content: str
    checksum: str | None
    updated_at: datetime | None


@dataclass(slots=True)
class KnowledgeSearchHit:
    """Represents one ranked file-level search match.

    ``score`` is the final fused score used for ranking.  When hybrid
    retrieval is active ``lexical_score`` and ``semantic_score`` hold the
    normalised sub-scores (each in [0, 1]) before blending, which aids
    debugging and observability.  Both are ``None`` for pure-lexical results.
    """

    file_id: str
    filename: str
    score: float
    snippet: str | None
    lexical_score: float | None = None
    semantic_score: float | None = None


@dataclass(slots=True)
class KnowledgeSearchResult:
    """Contains deterministic search output for a single query."""

    query: str
    hits: list[KnowledgeSearchHit]
