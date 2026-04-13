from collections.abc import Iterable, Mapping
from typing import Any

from app.domain.enums import MessageRole

DEFAULT_SYSTEM_PROMPT = (
    "You are a grounded QnA assistant backed by a knowledge base. "
    "Always search the knowledge base before concluding you cannot answer — even when it is unclear "
    "whether the answer is there. Never ask the user for clarification if a search could resolve the ambiguity. "
    "Search before reading full files, read only the files needed, and never rely on unstated assumptions. "
    "Keep answers faithful to retrieved content and say when the knowledge base does not support a claim. "
    "Decline any request that is clearly unrelated to the knowledge base domain — such as coding exercises, "
    "general trivia, or creative tasks — by responding: "
    "'This question is outside the scope of the knowledge base.'"
)

ProviderMessage = dict[str, Any]


def build_system_message(system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> ProviderMessage:
    """Build the provider system message."""
    return {
        "role": MessageRole.SYSTEM.value,
        "content": system_prompt,
    }


def build_chat_messages(
    history: Iterable[Any],
    user_message: Any,
    tool_messages: Iterable[Mapping[str, Any]] | None = None,
) -> list[ProviderMessage]:
    """Build provider-ready chat messages from internal history and optional tool results."""
    messages = [build_system_message()]
    messages.extend(_normalize_messages(history))
    messages.extend(_normalize_messages([user_message]))

    if tool_messages is not None:
        messages.extend(_normalize_messages(tool_messages))

    return messages


def _normalize_messages(messages: Iterable[Any]) -> list[ProviderMessage]:
    normalized_messages: list[ProviderMessage] = []

    for message in messages:
        normalized_messages.append(_normalize_message(message))

    return normalized_messages


def _normalize_message(message: Any) -> ProviderMessage:
    if isinstance(message, Mapping):
        payload = dict(message)
    else:
        payload = {
            "role": getattr(message, "role"),
            "content": getattr(message, "content"),
        }
        tool_call_id = getattr(message, "tool_call_id", None)
        name = getattr(message, "name", None)
        tool_calls = getattr(message, "tool_calls", None)

        if tool_call_id is not None:
            payload["tool_call_id"] = tool_call_id
        if name is not None:
            payload["name"] = name
        if tool_calls is not None:
            payload["tool_calls"] = tool_calls

    role = payload.get("role")
    content = payload.get("content")

    normalized_role = _normalize_role(role)
    if normalized_role != "assistant" and not isinstance(content, str):
        raise TypeError("Chat message content must be a string for non-assistant roles.")

    normalized_message: ProviderMessage = {
        "role": normalized_role,
        "content": content,
    }

    if "tool_call_id" in payload:
        normalized_message["tool_call_id"] = payload["tool_call_id"]

    if "name" in payload:
        normalized_message["name"] = payload["name"]

    if "tool_calls" in payload:
        normalized_message["tool_calls"] = payload["tool_calls"]

    return normalized_message


def _normalize_role(role: Any) -> str:
    if isinstance(role, MessageRole):
        return role.value

    if isinstance(role, str):
        normalized_role = role.strip().lower()
        if normalized_role in {"system", "user", "assistant", "tool"}:
            return normalized_role

    raise TypeError(f"Unsupported chat message role: {role!r}")
