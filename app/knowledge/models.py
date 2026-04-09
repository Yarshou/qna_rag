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
    """Represents one ranked file-level search match."""

    file_id: str
    filename: str
    score: float
    snippet: str | None


@dataclass(slots=True)
class KnowledgeSearchResult:
    """Contains deterministic search output for a single query."""

    query: str
    hits: list[KnowledgeSearchHit]
