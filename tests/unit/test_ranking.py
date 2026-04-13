"""Unit tests for the knowledge-base ranking and snippet helpers.

These tests exercise ranking.py in isolation — no file I/O, no LLM, no
network.  They verify the scoring formula, edge cases, and snippet extraction
logic against in-memory KnowledgeDocument instances.
"""

from datetime import UTC, datetime

from app.knowledge.models import KnowledgeDocument
from app.knowledge.ranking import build_snippet, score_document, tokenize

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


def test_tokenize_lowercases_and_splits_alphanumerics() -> None:
    tokens = tokenize("Hello World 123")
    assert tokens == ["hello", "world", "123"]


def test_tokenize_strips_punctuation() -> None:
    assert tokenize("hello, world!") == ["hello", "world"]


def test_tokenize_empty_string_returns_empty_list() -> None:
    assert tokenize("") == []


def test_tokenize_whitespace_only_returns_empty_list() -> None:
    assert tokenize("   ") == []


def test_score_returns_zero_for_empty_query() -> None:
    assert score_document(_doc("some content here"), "") == 0.0


def test_score_returns_zero_when_no_query_tokens_match() -> None:
    score = score_document(_doc("apples and oranges"), "zylophone quasar")
    assert score == 0.0


def test_score_returns_zero_for_empty_document_content() -> None:
    score = score_document(_doc(""), "readiness")
    assert score == 0.0


def test_score_positive_for_matching_content_token() -> None:
    score = score_document(_doc("The system uses readiness checks on startup"), "readiness")
    assert score > 0.0


def test_phrase_match_boosts_score_above_token_match() -> None:
    query = "readiness checks"
    doc_with_phrase = _doc("The deployment uses readiness checks before going live.")
    doc_without_phrase = _doc("readiness is important. checks are also important.")

    phrase_score = score_document(doc_with_phrase, query)
    token_score = score_document(doc_without_phrase, query)

    # Exact phrase match adds 4.0 bonus; it must dominate when both docs
    # have the same token coverage.
    assert phrase_score > token_score


def test_filename_bonus_increases_score() -> None:
    query = "deployment"
    doc_with_match_in_filename = _doc("some unrelated content", filename="deployment_notes.txt")
    doc_without_match_in_filename = _doc("some unrelated content", filename="general.txt")

    score_with = score_document(doc_with_match_in_filename, query)
    score_without = score_document(doc_without_match_in_filename, query)

    assert score_with > score_without


def test_higher_token_frequency_increases_score() -> None:
    query = "error"
    doc_many = _doc("error error error error error logs show error frequently")
    doc_few = _doc("there was an error once in the logs")

    assert score_document(doc_many, query) > score_document(doc_few, query)


def test_coverage_score_increases_with_more_matched_query_tokens() -> None:
    query = "startup readiness checks deployment"
    doc_all = _doc("startup readiness checks deployment procedures")
    doc_partial = _doc("startup notes only")

    assert score_document(doc_all, query) > score_document(doc_partial, query)


def test_duplicate_query_tokens_are_deduplicated_for_coverage() -> None:
    """Repeating the same token in the query should not inflate coverage."""
    query_repeated = "error error error"
    query_unique = "error"
    doc = _doc("There was an error in the system.")

    # Both queries have exactly one unique token; coverage scores must be equal.
    assert score_document(doc, query_repeated) == score_document(doc, query_unique)


def test_duplicate_query_tokens_are_deduplicated_for_phrase_bonus() -> None:
    query_repeated = "readiness readiness checks"
    query_unique = "readiness checks"
    doc = _doc("The deployment uses readiness checks before going live.")

    assert score_document(doc, query_repeated) == score_document(doc, query_unique)


def test_snippet_contains_query_token_context() -> None:
    doc = _doc("The system performs readiness checks before it accepts traffic.")
    snippet = build_snippet(doc, "readiness")

    assert snippet is not None
    assert "readiness" in snippet.lower()


def test_snippet_falls_back_to_prefix_when_no_token_matches() -> None:
    doc = _doc("A" * 300)
    snippet = build_snippet(doc, "zylophone")

    assert snippet is not None
    assert len(snippet) > 0
    assert snippet.endswith("...")


def test_snippet_adds_leading_ellipsis_when_context_starts_mid_document() -> None:
    # Put the query token well past the 60-char look-back window
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

    # Short content falls back to prefix; no trailing ellipsis needed.
    assert snippet == "Short doc."
    assert not snippet.endswith("...")
