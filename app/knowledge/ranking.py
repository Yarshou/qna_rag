"""Lexical scoring and snippet extraction for knowledge-base retrieval.

Scoring model
-------------
Each document receives a float score computed as the sum of four independent
signals.  Higher is better; zero means no query token matched anywhere.

1. **Coverage** (weight ×10) — fraction of unique query tokens that appear
   anywhere in the document (content *or* filename).  This is the primary
   signal: a document that mentions *all* query terms ranks higher than one
   that matches only some.

2. **Frequency** (weight ×1) — total occurrence count of query tokens in
   the document content, capped at ``_MAX_TOKEN_FREQUENCY`` per token.
   The cap prevents a single repeated term from dominating the score; the
   signal rewards documents where *multiple* query terms recur throughout.

3. **Filename bonus** (weight ×3) — query tokens that appear in the
   filename earn an extra multiplier because filenames are curated metadata
   and therefore a stronger relevance signal than body text.

4. **Phrase bonus** (flat +4.0) — when the entire normalised query string
   appears verbatim inside the content it indicates an exact match and earns
   a flat bonus on top of the component scores.

Tie-breaking
------------
Documents with equal scores are ordered deterministically by
``(filename ASC, id ASC)`` so that result lists are stable across calls.
"""

import re
from collections import Counter

from app.knowledge.models import KnowledgeDocument

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
WHITESPACE_PATTERN = re.compile(r"\s+")

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Target character window for the snippet shown to the model.
# ~180 chars ≈ 3–4 sentences — enough context without flooding the prompt.
SNIPPET_LENGTH = 180

# Characters to look back / ahead from the first matching token when building
# a snippet.  The combined window is intentionally asymmetric: more lookahead
# so the answer following the matched term is included.
_SNIPPET_LOOKBACK = 60
_SNIPPET_LOOKAHEAD = 100

# Per-token frequency contribution is capped to prevent a single repeated
# word (e.g. a term that appears in every paragraph) from dominating the
# frequency score at the expense of coverage diversity.
_MAX_TOKEN_FREQUENCY = 5

# Score weight applied to the coverage component.  Coverage is the most
# reliable signal so it receives the highest multiplier.
_COVERAGE_WEIGHT = 10.0

# Flat bonus awarded when the entire normalised query appears verbatim in
# the document content.  This rewards exact-phrase matches without
# compromising the additive nature of the scoring model.
_PHRASE_BONUS = 4.0

# Extra multiplier applied to filename token matches on top of the base
# frequency contribution.  Filenames are curated metadata and carry more
# signal per occurrence than body text.
_FILENAME_MULTIPLIER = 3


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def normalize_whitespace(value: str) -> str:
    """Collapse all whitespace runs to a single space and strip leading/trailing whitespace."""
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def tokenize(value: str) -> list[str]:
    """Extract lowercase alphanumeric tokens from *value*.

    Punctuation, special characters, and whitespace are discarded.  The
    result preserves insertion order and may contain duplicates.

    Examples
    --------
    >>> tokenize("Hello, World! 42")
    ['hello', 'world', '42']
    >>> tokenize("C++")
    ['c']
    """
    return TOKEN_PATTERN.findall(value.lower())


def score_document(document: KnowledgeDocument, query: str) -> float:
    """Return a non-negative relevance score for *document* against *query*.

    A score of ``0.0`` means no query token matched anywhere in the document.
    Scores are not normalised to a fixed range — they are only meaningful
    when compared against scores for *other* documents on the same query.

    Parameters
    ----------
    document:
        The knowledge document to evaluate.
    query:
        Raw user query string; tokenised internally.

    Returns
    -------
    float
        Additive score from the four components described in the module
        docstring.  Always ``≥ 0.0``.
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    # Deduplicate tokens while preserving order so that a repeated query word
    # does not artificially inflate the coverage denominator.
    unique_query_tokens = list(dict.fromkeys(query_tokens))

    filename_tokens = tokenize(document.filename)
    content_tokens = tokenize(document.content)
    token_counts = Counter(content_tokens)

    # A token is considered "matched" if it appears in the content OR in the
    # filename (filename match is handled separately in the scoring below).
    matched_tokens = [t for t in unique_query_tokens if token_counts[t] > 0 or t in filename_tokens]
    if not matched_tokens:
        return 0.0

    coverage_score = (len(matched_tokens) / len(unique_query_tokens)) * _COVERAGE_WEIGHT
    frequency_score = float(sum(min(token_counts[t], _MAX_TOKEN_FREQUENCY) for t in unique_query_tokens))
    filename_score = float(sum(1 for t in unique_query_tokens if t in filename_tokens) * _FILENAME_MULTIPLIER)

    normalized_query = normalize_whitespace(" ".join(unique_query_tokens))
    normalized_content = normalize_whitespace(document.content.lower())
    phrase_score = _PHRASE_BONUS if normalized_query and normalized_query in normalized_content else 0.0

    return coverage_score + frequency_score + filename_score + phrase_score


def build_snippet(document: KnowledgeDocument, query: str) -> str:
    """Extract a short, query-centred excerpt from *document*.

    The function finds the first query token that appears in the document and
    returns a window of text surrounding it (``_SNIPPET_LOOKBACK`` chars
    before, ``_SNIPPET_LOOKAHEAD`` chars after).  If no token matches, the
    first ``SNIPPET_LENGTH`` characters of the document are returned instead.

    Leading/trailing ellipses (``...``) are added when the window does not
    start at the document beginning or end at its end, respectively.

    Parameters
    ----------
    document:
        Source document from which to extract the snippet.
    query:
        Raw user query; its tokens are used to locate the anchor position.

    Returns
    -------
    str
        A short excerpt, at most ``SNIPPET_LENGTH + _SNIPPET_LOOKBACK +
        _SNIPPET_LOOKAHEAD`` characters long (plus optional ellipsis markers).
        Returns ``""`` for empty documents.
    """
    normalized_content = normalize_whitespace(document.content)
    if not normalized_content:
        return ""

    query_tokens = tokenize(query)
    # Case-fold only for searching; slices are taken from the original-case content.
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

    # Fallback: no token matched in the content — return the document prefix.
    excerpt = normalized_content[:SNIPPET_LENGTH].strip()
    if len(normalized_content) > SNIPPET_LENGTH:
        return f"{excerpt}..."
    return excerpt
