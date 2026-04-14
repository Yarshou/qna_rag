import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.domain import Message, MessageRole
from app.guardrails import InputGuard, OutputGuard
from app.knowledge import KnowledgeLoader, KnowledgeRetriever
from app.llm import (
    AzureOpenAIChatClient,
    LLMProviderError,
    ToolExecutionContext,
    ToolExecutor,
    build_chat_messages,
    get_knowledge_base_tools,
)
from app.repositories.messages import MessagesRepository
from app.services.chat_service import ChatService
from app.services.context_service import ContextService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class ChatNotFoundError(LookupError):
    """Raised when a requested chat does not exist."""


class MessageProcessingError(RuntimeError):
    """Raised when message orchestration cannot produce an assistant response."""


@dataclass(slots=True)
class MessageProcessingResult:
    """Stable service result for one user-message processing flow."""

    chat_id: str
    user_message: Message
    assistant_message: Message
    tool_calls_executed: int
    used_knowledge_files: list[str]


class MessageService:
    """Coordinates chat message persistence, tool-calling RAG, and lifecycle events."""

    def __init__(
        self,
        *,
        chat_service: ChatService | None = None,
        messages_repository: MessagesRepository | None = None,
        notification_service: NotificationService | None = None,
        context_service: ContextService | None = None,
        llm_client: AzureOpenAIChatClient | None = None,
        tool_executor: ToolExecutor | None = None,
        input_guard: InputGuard | None = None,
        output_guard: OutputGuard | None = None,
        max_tool_round_trips: int | None = None,
    ) -> None:
        self._chat_service = chat_service or ChatService()
        self._messages_repository = messages_repository or MessagesRepository()
        self._notification_service = notification_service or NotificationService()
        self._context_service = context_service or ContextService(self._messages_repository)
        self._llm_client = llm_client or AzureOpenAIChatClient()
        self._tool_executor = tool_executor or self._build_tool_executor()
        self._input_guard = input_guard or InputGuard()
        self._output_guard = output_guard or OutputGuard()
        self._max_tool_round_trips = max_tool_round_trips if max_tool_round_trips is not None else settings.MAX_TOOL_ROUND_TRIPS

    async def list_messages(self, chat_id: str, *, limit: int = 50, offset: int = 0) -> tuple[list[Message], int]:
        await self._ensure_chat_exists(chat_id)
        rows, total = await asyncio.gather(
            self._messages_repository.list_messages(chat_id, limit=limit, offset=offset),
            self._messages_repository.count_messages(chat_id),
        )
        return [Message.from_mapping(row) for row in rows], total

    async def post_user_message(self, chat_id: str, content: str) -> MessageProcessingResult:
        await self._ensure_chat_exists(chat_id)

        user_message = Message.from_mapping(
            await self._messages_repository.create_message(
                chat_id=chat_id,
                role=MessageRole.USER.value,
                content=content,
            )
        )
        failure_payload: dict[str, object] = {"message_id": user_message.id}

        try:
            logger.info("message_processing_started", extra={"chat_id": chat_id, "message_id": user_message.id})
            await self._notification_service.emit_message_received(chat_id, payload=failure_payload)
            await self._notification_service.emit_message_processing(chat_id, payload=failure_payload)

            history = await self._context_service.get_chat_history(chat_id)
            prior_history = self._exclude_current_user_message(history=history, user_message=user_message)
            provider_messages = build_chat_messages(history=prior_history, user_message=user_message)

            self._input_guard.check(content)
            assistant_content, tool_calls_executed, used_knowledge_files = await self._run_agent_flow(
                chat_id=chat_id,
                provider_messages=provider_messages,
            )
            assistant_content = self._output_guard.check(assistant_content, tool_calls_executed)

            assistant_metadata = {
                "tool_calls_executed": tool_calls_executed,
                "used_knowledge_files": used_knowledge_files,
            }
            assistant_message = Message.from_mapping(
                await self._messages_repository.create_message(
                    chat_id=chat_id,
                    role=MessageRole.ASSISTANT.value,
                    content=assistant_content,
                    metadata=assistant_metadata,
                )
            )

            await self._notification_service.emit_message_completed(
                chat_id,
                payload={
                    "message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "tool_calls_executed": tool_calls_executed,
                    "used_knowledge_files": used_knowledge_files,
                },
            )
            logger.info(
                "message_processing_completed",
                extra={
                    "chat_id": chat_id,
                    "message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "tool_calls_executed": tool_calls_executed,
                    "used_knowledge_files_count": len(used_knowledge_files),
                },
            )
            return MessageProcessingResult(
                chat_id=chat_id,
                user_message=user_message,
                assistant_message=assistant_message,
                tool_calls_executed=tool_calls_executed,
                used_knowledge_files=used_knowledge_files,
            )
        except Exception as exc:
            await self._emit_failure_event(chat_id=chat_id, payload={**failure_payload, "error": str(exc)})
            if isinstance(exc, (LLMProviderError, MessageProcessingError)):
                raise
            raise MessageProcessingError("Failed to process user message.") from exc

    async def _run_agent_flow(
        self,
        *,
        chat_id: str,
        provider_messages: list[dict[str, Any]],
    ) -> tuple[str, int, list[str]]:
        conversation = list(provider_messages)
        tools = get_knowledge_base_tools()
        tool_calls_executed = 0
        used_knowledge_files: list[str] = []
        tool_ctx = ToolExecutionContext()

        for _ in range(self._max_tool_round_trips):
            logger.info(
                "llm_chat_completion_started",
                extra={"chat_id": chat_id, "messages": len(conversation), "tools_enabled": True},
            )
            response = await self._llm_client.create_chat_completion_async(
                messages=conversation,
                tools=tools,
            )
            assistant_message = self._llm_client.extract_first_message(response)
            tool_calls = list(getattr(assistant_message, "tool_calls", None) or [])

            if not tool_calls:
                assistant_content = self._extract_assistant_content(assistant_message)
                return assistant_content, tool_calls_executed, used_knowledge_files

            conversation.append(self._provider_message_to_mapping(assistant_message))

            for tool_call in tool_calls:
                tool_name = getattr(getattr(tool_call, "function", None), "name", None)
                arguments = getattr(getattr(tool_call, "function", None), "arguments", None)
                tool_result = self._tool_executor.execute_tool_call(tool_name, arguments, tool_ctx)
                tool_message = self._build_tool_message(tool_call=tool_call, tool_name=tool_name, tool_result=tool_result)
                conversation.append(tool_message)
                tool_calls_executed += 1

                used_file_id = self._extract_used_knowledge_file(tool_name=tool_name, tool_result=tool_result)
                if used_file_id is not None and used_file_id not in used_knowledge_files:
                    used_knowledge_files.append(used_file_id)

                await self._notification_service.emit_tool_called(
                    chat_id,
                    payload={
                        "tool_call_id": getattr(tool_call, "id", None),
                        "tool_name": tool_name,
                        "used_file_id": used_file_id,
                    },
                )

            logger.info(
                "tool_round_completed",
                extra={
                    "chat_id": chat_id,
                    "tool_calls_executed": tool_calls_executed,
                    "used_knowledge_files_count": len(used_knowledge_files),
                },
            )

        raise MessageProcessingError("Assistant exceeded the allowed tool-calling rounds.")

    async def _ensure_chat_exists(self, chat_id: str) -> None:
        if await self._chat_service.get_chat(chat_id) is None:
            raise ChatNotFoundError(f"Chat '{chat_id}' was not found.")

    @staticmethod
    def _exclude_current_user_message(history: list[Message], user_message: Message) -> list[Message]:
        if history and history[-1].id == user_message.id:
            return history[:-1]
        return history

    @staticmethod
    def _provider_message_to_mapping(message: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": getattr(message, "role"),
            "content": getattr(message, "content", None),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls is not None:
            payload["tool_calls"] = [MessageService._tool_call_to_mapping(tool_call) for tool_call in tool_calls]
        return payload

    @staticmethod
    def _tool_call_to_mapping(tool_call: Any) -> dict[str, Any]:
        function_payload = getattr(tool_call, "function", None)
        return {
            "id": getattr(tool_call, "id", None),
            "type": getattr(tool_call, "type", "function"),
            "function": {
                "name": getattr(function_payload, "name", None),
                "arguments": getattr(function_payload, "arguments", None),
            },
        }

    @staticmethod
    def _build_tool_message(tool_call: Any, tool_name: str | None, tool_result: Mapping[str, Any]) -> dict[str, str]:
        tool_call_id = getattr(tool_call, "id", None)
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise MessageProcessingError("Provider returned a tool call without a valid id.")
        if not isinstance(tool_name, str) or not tool_name:
            raise MessageProcessingError("Provider returned a tool call without a valid function name.")

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps(tool_result, ensure_ascii=True),
        }

    @staticmethod
    def _extract_assistant_content(message: Any) -> str:
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise MessageProcessingError("Assistant response did not include textual content.")
        return content

    @staticmethod
    def _extract_used_knowledge_file(tool_name: str | None, tool_result: Mapping[str, Any]) -> str | None:
        if tool_name != "read_knowledge_file":
            return None
        document = tool_result.get("document")
        if not isinstance(document, Mapping):
            return None
        document_id = document.get("id")
        return document_id if isinstance(document_id, str) and document_id else None

    async def _emit_failure_event(self, *, chat_id: str, payload: Mapping[str, object]) -> None:
        try:
            await self._notification_service.emit_message_failed(chat_id, payload=payload)
        except Exception as exc:  # pragma: no cover - best-effort failure reporting
            logger.warning(
                "message_failed_event_emission_failed",
                extra={"chat_id": chat_id, "error_type": exc.__class__.__name__},
            )

    @staticmethod
    def _build_tool_executor() -> ToolExecutor:
        if settings.KNOWLEDGE_DIR is None:
            raise MessageProcessingError("KNOWLEDGE_DIR is not configured.")

        loader = KnowledgeLoader(settings.KNOWLEDGE_DIR)
        retriever = KnowledgeRetriever(loader)
        return ToolExecutor(retriever)
