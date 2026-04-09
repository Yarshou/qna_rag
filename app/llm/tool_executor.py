import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol

from app.knowledge import MAX_KNOWLEDGE_FILES_IN_CONTEXT
from app.knowledge.models import KnowledgeDocument, KnowledgeSearchResult
from app.llm.exceptions import InvalidToolArgumentsError, UnsupportedToolError

logger = logging.getLogger(__name__)


class KnowledgeAccessProtocol(Protocol):
    """Minimal knowledge access contract required by the tool executor."""

    def search_knowledge_base(self, query: str, limit: int = 5) -> KnowledgeSearchResult: ...

    def read_knowledge_file(self, file_id: str) -> KnowledgeDocument | None: ...


class ToolExecutor:
    """Execute supported knowledge-base tool calls through the knowledge layer."""

    def __init__(self, knowledge_access: KnowledgeAccessProtocol) -> None:
        self._knowledge_access = knowledge_access
        self._full_file_reads = 0

    def execute_tool_call(self, tool_name: str, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        """Execute one tool call and return a structured result payload."""
        parsed_arguments = self._parse_arguments(arguments)

        if tool_name == "search_knowledge_base":
            return self._execute_search(parsed_arguments)

        if tool_name == "read_knowledge_file":
            return self._execute_read(parsed_arguments)

        raise UnsupportedToolError(f"Unsupported tool: {tool_name}")

    def execute_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        """Execute provider tool calls and return tool messages ready for chat history."""
        tool_messages: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            function_payload = getattr(tool_call, "function", None)
            if function_payload is None:
                raise InvalidToolArgumentsError("Tool call is missing function payload.")

            tool_name = getattr(function_payload, "name", None)
            if not isinstance(tool_name, str) or not tool_name:
                raise InvalidToolArgumentsError("Tool call is missing a valid function name.")

            arguments = getattr(function_payload, "arguments", None)
            result = self.execute_tool_call(tool_name, arguments)
            tool_call_id = getattr(tool_call, "id", None)
            if not isinstance(tool_call_id, str) or not tool_call_id:
                raise InvalidToolArgumentsError("Tool call is missing a valid tool call id.")

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=True),
                }
            )

        return tool_messages

    @staticmethod
    def _parse_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if arguments is None:
            return {}

        if isinstance(arguments, dict):
            return arguments

        if not isinstance(arguments, str):
            raise InvalidToolArgumentsError("Tool arguments must be a JSON object string.")

        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise InvalidToolArgumentsError("Tool arguments must be valid JSON.") from exc

        if not isinstance(parsed_arguments, dict):
            raise InvalidToolArgumentsError("Tool arguments must decode to a JSON object.")

        return parsed_arguments

    def _execute_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        limit = arguments.get("limit", 5)

        if not isinstance(query, str) or not query.strip():
            raise InvalidToolArgumentsError("search_knowledge_base requires a non-empty string query.")

        if not isinstance(limit, int):
            raise InvalidToolArgumentsError("search_knowledge_base limit must be an integer.")

        if limit < 1:
            raise InvalidToolArgumentsError("search_knowledge_base limit must be at least 1.")

        result = self._knowledge_access.search_knowledge_base(query=query.strip(), limit=limit)
        logger.info(
            "knowledge_tool_search_executed",
            extra={"tool_name": "search_knowledge_base", "limit": limit, "hits": len(result.hits)},
        )
        return self._serialize_result(result)

    def _execute_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_id = arguments.get("file_id")
        if not isinstance(file_id, str) or not file_id.strip():
            raise InvalidToolArgumentsError("read_knowledge_file requires a non-empty string file_id.")

        if self._full_file_reads >= MAX_KNOWLEDGE_FILES_IN_CONTEXT:
            raise InvalidToolArgumentsError(
                f"read_knowledge_file is limited to {MAX_KNOWLEDGE_FILES_IN_CONTEXT} files per execution flow."
            )

        document = self._knowledge_access.read_knowledge_file(file_id=file_id.strip())
        self._full_file_reads += 1
        logger.info(
            "knowledge_tool_read_executed",
            extra={
                "tool_name": "read_knowledge_file",
                "file_id": file_id.strip(),
                "read_count": self._full_file_reads,
                "found": document is not None,
            },
        )

        if document is None:
            return {
                "file_id": file_id.strip(),
                "found": False,
                "content": None,
            }

        return {
            "found": True,
            "document": self._serialize_result(document),
        }

    def reset_context_limits(self) -> None:
        """Reset per-flow read counters before starting a new tool-calling pass."""
        self._full_file_reads = 0

    @staticmethod
    def _serialize_result(value: Any) -> Any:
        if is_dataclass(value):
            serialized = asdict(value)
        else:
            serialized = value

        if isinstance(serialized, dict):
            return {key: ToolExecutor._serialize_result(item) for key, item in serialized.items()}

        if isinstance(serialized, list):
            return [ToolExecutor._serialize_result(item) for item in serialized]

        if hasattr(serialized, "isoformat"):
            return serialized.isoformat()

        return serialized
