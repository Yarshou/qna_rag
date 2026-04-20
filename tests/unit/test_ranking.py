"""Unit tests for the stateless ranking helpers."""

from datetime import UTC, datetime

from app.knowledge.models import KnowledgeDocument
from app.knowledge.ranking import (
    build_snippet,
    cosine_scores,
    min_max_normalize,
    tokenize,
)

_FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(content: str, filename: str = "notes.txt") -> KnowledgeDocument:
    return KnowledgeDocument(
        id="doc-1",
        filename=filename,
        path=filename,
        content=content,
        checksum="abc",
        updated_at=_FIXED_TIME,
    )


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_tokenize_lowercases_and_splits_alphanumerics() -> None:
    assert tokenize("Hello World 123") == ["hello", "world", "123"]


def test_tokenize_strips_punctuation() -> None:
    assert tokenize("hello, world!") == ["hello", "world"]


def test_tokenize_empty_string_returns_empty_list() -> None:
    assert tokenize("") == []


def test_tokenize_whitespace_only_returns_empty_list() -> None:
    assert tokenize("   ") == []


def test_tokenize_drops_special_characters() -> None:
    # Important for FTS5 safety: "C++ !!" must sanitise to ["c"].
    assert tokenize("C++ !!") == ["c"]


# ---------------------------------------------------------------------------
# build_snippet
# ---------------------------------------------------------------------------


def test_snippet_contains_query_token_context() -> None:
    doc = _doc("The system performs readiness checks before it accepts traffic.")
    snippet = build_snippet(doc, "readiness")

    assert snippet
    assert "readiness" in snippet.lower()


def test_snippet_falls_back_to_prefix_when_no_token_matches() -> None:
    doc = _doc("A" * 300)
    snippet = build_snippet(doc, "zylophone")
    assert snippet.endswith("...")


def test_snippet_adds_leading_ellipsis_when_context_starts_mid_document() -> None:
    prefix = "x" * 200
    doc = _doc(f"{prefix} readiness checks are important")
    snippet = build_snippet(doc, "readiness")
    assert snippet.startswith("...")


def test_snippet_adds_trailing_ellipsis_when_content_continues_past_match() -> None:
    suffix = "y" * 200
    doc = _doc(f"readiness checks are done. {suffix}")
    snippet = build_snippet(doc, "readiness")
    assert snippet.endswith("...")


def test_snippet_for_empty_document_returns_empty_string() -> None:
    assert build_snippet(_doc(""), "readiness") == ""


def test_snippet_for_short_content_returns_full_content_without_ellipsis() -> None:
    doc = _doc("Short doc.")
    snippet = build_snippet(doc, "xyz_no_match")
    assert snippet == "Short doc."
    assert not snippet.endswith("...")


# ---------------------------------------------------------------------------
# min_max_normalize
# ---------------------------------------------------------------------------


def test_min_max_normalize_empty_list() -> None:
    assert min_max_normalize([]) == []


def test_min_max_normalize_all_equal_returns_zeros() -> None:
    assert min_max_normalize([3.0, 3.0, 3.0]) == [0.0, 0.0, 0.0]


def test_min_max_normalize_single_element_returns_zero() -> None:
    assert min_max_normalize([5.0]) == [0.0]


def test_min_max_normalize_range_is_zero_to_one() -> None:
    result = min_max_normalize([0.0, 5.0, 10.0])
    assert result[0] == 0.0
    assert result[-1] == 1.0
    assert 0.0 < result[1] < 1.0


def test_min_max_normalize_preserves_order() -> None:
    normalized = min_max_normalize([1.0, 3.0, 2.0])
    assert normalized[0] < normalized[2] < normalized[1]


# ---------------------------------------------------------------------------
# cosine_scores
# ---------------------------------------------------------------------------


def test_cosine_scores_identical_unit_vector_returns_one() -> None:
    q = [1.0, 0.0, 0.0]
    scores = cosine_scores(q, [q])
    assert abs(scores[0] - 1.0) < 1e-6


def test_cosine_scores_orthogonal_vectors_returns_zero() -> None:
    scores = cosine_scores([1.0, 0.0], [[0.0, 1.0]])
    assert abs(scores[0]) < 1e-6


def test_cosine_scores_opposite_vectors_returns_minus_one() -> None:
    scores = cosine_scores([1.0, 0.0], [[-1.0, 0.0]])
    assert abs(scores[0] - (-1.0)) < 1e-6


def test_cosine_scores_empty_doc_list_returns_empty() -> None:
    assert cosine_scores([1.0, 0.0], []) == []


def test_cosine_scores_handles_zero_vector_without_nan() -> None:
    scores = cosine_scores([1.0, 0.0], [[0.0, 0.0], [1.0, 0.0]])
    assert scores[0] == 0.0
    assert abs(scores[1] - 1.0) < 1e-6


def test_cosine_scores_batch_preserves_order() -> None:
    q = [1.0, 0.0, 0.0]
    docs = [
        [1.0, 0.0, 0.0],  # dot = 1
        [0.0, 1.0, 0.0],  # dot = 0
        [-1.0, 0.0, 0.0],  # dot = -1
    ]
    scores = cosine_scores(q, docs)
    assert scores[0] > scores[1] > scores[2]
