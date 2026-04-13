from datetime import UTC, datetime

import pytest

from app.knowledge import MAX_KNOWLEDGE_FILES_IN_CONTEXT
from app.knowledge.models import KnowledgeDocument, KnowledgeSearchHit, KnowledgeSearchResult
from app.llm.exceptions import InvalidToolArgumentsError
from app.llm.tool_executor import ToolExecutor

FIXED_UPDATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class FakeKnowledgeAccess:
    def __init__(self) -> None:
        self._documents = {
            "file-a": self._build_document("file-a", "alpha.txt", "Alpha content"),
            "file-b": self._build_document("file-b", "beta.txt", "Beta content"),
            "file-c": self._build_document("file-c", "gamma.txt", "Gamma content"),
        }
        self._search_results = {
            "alpha": ["file-a", "file-b"],
            "beta": ["file-c"],
            "all": ["file-a", "file-b", "file-c"],
        }

    def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult:
        file_ids = self._search_results.get(query, [])[:limit]
        hits = [
            KnowledgeSearchHit(
                file_id=file_id,
                filename=self._documents[file_id].filename,
                score=round(1.0 - (index * 0.1), 4),
                snippet=f"Snippet for {file_id}",
            )
            for index, file_id in enumerate(file_ids)
        ]
        return KnowledgeSearchResult(query=query, hits=hits)

    def read_knowledge_file(self, file_id: str) -> KnowledgeDocument | None:
        return self._documents.get(file_id)

    @staticmethod
    def _build_document(file_id: str, filename: str, content: str) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=file_id,
            filename=filename,
            path=filename,
            content=content,
            checksum=f"checksum-{file_id}",
            updated_at=FIXED_UPDATED_AT,
        )


def test_read_requires_prior_search() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="prior successful search_knowledge_base"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"})


def test_read_rejects_file_not_returned_by_last_search() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2})

    with pytest.raises(InvalidToolArgumentsError, match="last successful search_knowledge_base"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"})


def test_new_search_replaces_previous_allowed_file_ids() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2})
    executor.execute_tool_call("search_knowledge_base", {"query": "beta", "limit": 1})

    with pytest.raises(InvalidToolArgumentsError, match="last successful search_knowledge_base"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"})

    result = executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"})

    assert result["found"] is True
    assert result["document"]["id"] == "file-c"


def test_search_then_read_succeeds() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    search_result = executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2})
    read_result = executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"})

    assert [hit["file_id"] for hit in search_result["hits"]] == ["file-a", "file-b"]
    assert read_result["found"] is True
    assert read_result["document"]["id"] == "file-a"
    assert read_result["document"]["content"] == "Alpha content"


def test_read_limit_is_preserved() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    executor.execute_tool_call("search_knowledge_base", {"query": "all", "limit": 3})
    executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"})
    executor.execute_tool_call("read_knowledge_file", {"file_id": "file-b"})

    with pytest.raises(InvalidToolArgumentsError, match=f"limited to {MAX_KNOWLEDGE_FILES_IN_CONTEXT}"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"})


def test_reset_context_limits_clears_allowed_file_ids() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2})
    executor.reset_context_limits()

    with pytest.raises(InvalidToolArgumentsError, match="prior successful search_knowledge_base"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"})


def test_search_with_empty_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        executor.execute_tool_call("search_knowledge_base", {"query": ""})


def test_search_with_whitespace_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        executor.execute_tool_call("search_knowledge_base", {"query": "   "})


def test_search_with_missing_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        executor.execute_tool_call("search_knowledge_base", {})


def test_search_with_non_integer_limit_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="limit must be an integer"):
        executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": "five"})


def test_search_with_zero_limit_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="limit must be at least"):
        executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 0})


def test_search_with_json_string_arguments() -> None:
    """Arguments may arrive as a JSON-encoded string from the provider."""
    import json

    executor = ToolExecutor(FakeKnowledgeAccess())
    result = executor.execute_tool_call("search_knowledge_base", json.dumps({"query": "alpha", "limit": 1}))

    assert len(result["hits"]) == 1
    assert result["hits"][0]["file_id"] == "file-a"


def test_search_with_invalid_json_string_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="valid JSON"):
        executor.execute_tool_call("search_knowledge_base", "{bad json}")


def test_read_with_empty_file_id_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    executor.execute_tool_call("search_knowledge_base", {"query": "alpha"})

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string file_id"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": ""})


def test_read_with_whitespace_file_id_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    executor.execute_tool_call("search_knowledge_base", {"query": "alpha"})

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string file_id"):
        executor.execute_tool_call("read_knowledge_file", {"file_id": "   "})


def test_read_missing_file_returns_not_found_payload() -> None:
    """read_knowledge_file for a valid but absent file must return found=False."""
    executor = ToolExecutor(FakeKnowledgeAccess())
    # Search returns file-a and file-b; use a file_id that exists in the
    # allowlist but not in the fake document store.
    executor._allowed_file_ids = {"nonexistent-file"}  # bypass allowlist check
    executor._full_file_reads = 0

    result = executor.execute_tool_call("read_knowledge_file", {"file_id": "nonexistent-file"})

    assert result["found"] is False
    assert result["content"] is None


def test_unsupported_tool_raises_error() -> None:
    from app.llm.exceptions import UnsupportedToolError

    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(UnsupportedToolError, match="Unsupported tool"):
        executor.execute_tool_call("delete_all_files", {})


def test_execute_tool_calls_returns_tool_messages() -> None:
    """execute_tool_calls must wrap each result in a tool-role message dict."""

    class _FakeToolCall:
        def __init__(self, call_id: str, name: str, args: str) -> None:
            self.id = call_id
            self.type = "function"

            class _Fn:
                pass

            fn = _Fn()
            fn.name = name
            fn.arguments = args
            self.function = fn

    executor = ToolExecutor(FakeKnowledgeAccess())
    import json

    tool_calls = [_FakeToolCall("call-1", "search_knowledge_base", json.dumps({"query": "alpha", "limit": 2}))]

    messages = executor.execute_tool_calls(tool_calls)

    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call-1"
    assert msg["name"] == "search_knowledge_base"
    payload = json.loads(msg["content"])
    assert "hits" in payload
