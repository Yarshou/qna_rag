from datetime import UTC, datetime

import pytest

from app.knowledge import MAX_KNOWLEDGE_FILES_IN_CONTEXT
from app.knowledge.models import KnowledgeDocument, KnowledgeSearchHit, KnowledgeSearchResult
from app.llm.exceptions import InvalidToolArgumentsError
from app.llm.tool_executor import ToolExecutionContext, ToolExecutor

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

    async def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult:
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

    async def read_knowledge_file(self, file_id: str) -> KnowledgeDocument | None:
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


@pytest.mark.anyio
async def test_read_requires_prior_search() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()

    with pytest.raises(InvalidToolArgumentsError, match="prior successful search_knowledge_base"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx)


@pytest.mark.anyio
async def test_read_rejects_file_not_returned_by_last_search() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()

    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2}, ctx)

    with pytest.raises(InvalidToolArgumentsError, match="last successful search_knowledge_base"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"}, ctx)


@pytest.mark.anyio
async def test_new_search_replaces_previous_allowed_file_ids() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()

    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2}, ctx)
    await executor.execute_tool_call("search_knowledge_base", {"query": "beta", "limit": 1}, ctx)

    with pytest.raises(InvalidToolArgumentsError, match="last successful search_knowledge_base"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx)

    result = await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"}, ctx)

    assert result["found"] is True
    assert result["document"]["id"] == "file-c"


@pytest.mark.anyio
async def test_search_then_read_succeeds() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()

    search_result = await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2}, ctx)
    read_result = await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx)

    assert [hit["file_id"] for hit in search_result["hits"]] == ["file-a", "file-b"]
    assert read_result["found"] is True
    assert read_result["document"]["id"] == "file-a"
    assert read_result["document"]["content"] == "Alpha content"


@pytest.mark.anyio
async def test_read_limit_is_preserved() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()

    await executor.execute_tool_call("search_knowledge_base", {"query": "all", "limit": 3}, ctx)
    await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx)
    await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-b"}, ctx)

    with pytest.raises(InvalidToolArgumentsError, match=f"limited to {MAX_KNOWLEDGE_FILES_IN_CONTEXT}"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"}, ctx)


@pytest.mark.anyio
async def test_fresh_context_has_no_allowed_file_ids() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    ctx_a = ToolExecutionContext()
    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2}, ctx_a)
    await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx_a)

    ctx_b = ToolExecutionContext()
    with pytest.raises(InvalidToolArgumentsError, match="prior successful search_knowledge_base"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx_b)


@pytest.mark.anyio
async def test_two_concurrent_contexts_are_isolated() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    ctx_a = ToolExecutionContext()
    ctx_b = ToolExecutionContext()

    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 2}, ctx_a)
    await executor.execute_tool_call("search_knowledge_base", {"query": "beta", "limit": 1}, ctx_b)

    result_a = await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx_a)
    assert result_a["found"] is True

    with pytest.raises(InvalidToolArgumentsError, match="last successful search_knowledge_base"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-a"}, ctx_b)

    result_b = await executor.execute_tool_call("read_knowledge_file", {"file_id": "file-c"}, ctx_b)
    assert result_b["found"] is True


@pytest.mark.anyio
async def test_search_with_empty_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        await executor.execute_tool_call("search_knowledge_base", {"query": ""}, ToolExecutionContext())


@pytest.mark.anyio
async def test_search_with_whitespace_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        await executor.execute_tool_call("search_knowledge_base", {"query": "   "}, ToolExecutionContext())


@pytest.mark.anyio
async def test_search_with_missing_query_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string query"):
        await executor.execute_tool_call("search_knowledge_base", {}, ToolExecutionContext())


@pytest.mark.anyio
async def test_search_with_non_integer_limit_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="limit must be an integer"):
        await executor.execute_tool_call(
            "search_knowledge_base", {"query": "alpha", "limit": "five"}, ToolExecutionContext()
        )


@pytest.mark.anyio
async def test_search_with_zero_limit_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="limit must be at least"):
        await executor.execute_tool_call("search_knowledge_base", {"query": "alpha", "limit": 0}, ToolExecutionContext())


@pytest.mark.anyio
async def test_search_with_json_string_arguments() -> None:
    import json

    executor = ToolExecutor(FakeKnowledgeAccess())
    result = await executor.execute_tool_call(
        "search_knowledge_base", json.dumps({"query": "alpha", "limit": 1}), ToolExecutionContext()
    )

    assert len(result["hits"]) == 1
    assert result["hits"][0]["file_id"] == "file-a"


@pytest.mark.anyio
async def test_search_with_invalid_json_string_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(InvalidToolArgumentsError, match="valid JSON"):
        await executor.execute_tool_call("search_knowledge_base", "{bad json}", ToolExecutionContext())


@pytest.mark.anyio
async def test_read_with_empty_file_id_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()
    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha"}, ctx)

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string file_id"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": ""}, ctx)


@pytest.mark.anyio
async def test_read_with_whitespace_file_id_raises_error() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext()
    await executor.execute_tool_call("search_knowledge_base", {"query": "alpha"}, ctx)

    with pytest.raises(InvalidToolArgumentsError, match="non-empty string file_id"):
        await executor.execute_tool_call("read_knowledge_file", {"file_id": "   "}, ctx)


@pytest.mark.anyio
async def test_read_missing_file_returns_not_found_payload() -> None:
    executor = ToolExecutor(FakeKnowledgeAccess())
    ctx = ToolExecutionContext(allowed_file_ids={"nonexistent-file"})

    result = await executor.execute_tool_call("read_knowledge_file", {"file_id": "nonexistent-file"}, ctx)

    assert result["found"] is False
    assert result["content"] is None


@pytest.mark.anyio
async def test_unsupported_tool_raises_error() -> None:
    from app.llm.exceptions import UnsupportedToolError

    executor = ToolExecutor(FakeKnowledgeAccess())

    with pytest.raises(UnsupportedToolError, match="Unsupported tool"):
        await executor.execute_tool_call("delete_all_files", {}, ToolExecutionContext())


@pytest.mark.anyio
async def test_execute_tool_calls_returns_tool_messages() -> None:
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

    messages = await executor.execute_tool_calls(tool_calls, ToolExecutionContext())

    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call-1"
    assert msg["name"] == "search_knowledge_base"
    payload = json.loads(msg["content"])
    assert "hits" in payload
