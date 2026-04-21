"""Text-processing and score-fusion helpers for the hybrid retriever.

Contains the stateless primitives shared between indexing and retrieval:

* :func:`tokenize` — lowercase alphanumeric tokens, used to sanitize queries
  before passing them to SQLite FTS5.
* :func:`build_snippet` — build a short, query-centred excerpt of a document
  for display in search results.
* :func:`min_max_normalize` — rescale a list of scores to ``[0, 1]`` so that
  BM25 and cosine signals can be fused on a common scale.
* :func:`cosine_scores` — compute cosine similarity between a query vector
  and a batch of document vectors using NumPy.
"""

import re

import numpy as np

from app.knowledge.models import KnowledgeDocument

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
WHITESPACE_PATTERN = re.compile(r"\s+")

SNIPPET_LENGTH = 180
_SNIPPET_LOOKBACK = 60
_SNIPPET_LOOKAHEAD = 100


def normalize_whitespace(value: str) -> str:
    """Collapse all whitespace runs to a single space and strip ends."""
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def tokenize(value: str) -> list[str]:
    """Extract lowercase alphanumeric tokens from *value*."""
    return TOKEN_PATTERN.findall(value.lower())


def build_snippet(document: KnowledgeDocument, query: str) -> str:
    """Extract a short, query-centred excerpt from *document*."""
    normalized_content = normalize_whitespace(document.content)
    if not normalized_content:
        return ""

    query_tokens = tokenize(query)
    lowered_content = normalized_content.lower()

    for token in query_tokens:
        match_index = lowered_content.find(token)
        if match_index < 0:
            continue

        start = max(0, match_index - _SNIPPET_LOOKBACK)
        end = min(len(normalized_content), match_index + len(token) + _SNIPPET_LOOKAHEAD)
        snippet = normalized_content[start:end].strip()

        if start > 0:
            snippet = f"...{snippet}"
        if end < len(normalized_content):
            snippet = f"{snippet}..."

        return snippet

    excerpt = normalized_content[:SNIPPET_LENGTH].strip()
    if len(normalized_content) > SNIPPET_LENGTH:
        return f"{excerpt}..."
    return excerpt


def build_snippet_from_content(content: str, query: str) -> str:
    """Snippet helper when only the raw content string is available."""
    doc = KnowledgeDocument(
        id="",
        filename="",
        path="",
        content=content,
        checksum=None,
        updated_at=None,
    )
    return build_snippet(doc, query)


def min_max_normalize(scores: list[float]) -> list[float]:
    """Normalize *scores* to ``[0, 1]`` using min-max scaling."""
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi == lo:
        return [0.0] * len(scores)
    span = hi - lo
    return [(s - lo) / span for s in scores]


def cosine_scores(query_vec: list[float], doc_vecs: list[list[float]]) -> list[float]:
    """Batch cosine similarity between *query_vec* and each of *doc_vecs*.

    OpenAI embeddings are already L2-normalized so the dot product is
    equivalent to cosine similarity.  For provider-agnostic correctness we
    still divide by the vector magnitudes when they are not unit-length.
    """
    if not doc_vecs or not query_vec:
        return [0.0] * len(doc_vecs)

    query = np.asarray(query_vec, dtype=np.float32)
    doc_matrix = np.asarray(doc_vecs, dtype=np.float32)
    query_norm = float(np.linalg.norm(query))
    if query_norm == 0.0:
        return [0.0] * len(doc_vecs)

    dot_products = doc_matrix @ query
    doc_norms = np.linalg.norm(doc_matrix, axis=1)
    # Avoid division-by-zero for degenerate zero vectors.
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(
            doc_norms > 0,
            dot_products / (doc_norms * query_norm),
            0.0,
        )
    return scores.astype(float).tolist()
