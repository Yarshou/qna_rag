"""System prompt definition and provider message normalisation utilities.

The module owns two concerns:

1. **System prompt** — ``DEFAULT_SYSTEM_PROMPT`` encodes the agent's
   behavioural contract: always search before reading, stay grounded in the
   knowledge base, and decline out-of-scope requests.

2. **Message normalisation** — :func:`build_chat_messages` assembles a
   provider-ready message list from a mix of common_types objects
   (:class:`~app.common_types.models.Message`) and plain dicts.  This lets the
   service layer stay decoupled from the exact wire format expected by the
   OpenAI chat-completions API.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from app.common_types.enums import MessageRole

# A provider message is a plain dict with at minimum ``role`` and ``content``
# keys, matching the OpenAI chat-completions wire format.  Using a type alias
# rather than a TypedDict keeps downstream code simpler while still
# communicating intent.
ProviderMessage = dict[str, Any]

DEFAULT_SYSTEM_PROMPT = (
    "You are a grounded QnA assistant backed by a knowledge base. "
    "Always search the knowledge base before concluding you cannot answer — even when it is unclear "
    "whether the answer is there. Never ask the user for clarification if a search could resolve the ambiguity. "
    "Search before reading full files, read only the files needed, and never rely on unstated assumptions. "
    "Keep answers faithful to retrieved content and say when the knowledge base does not support a claim. "
    "Decline any request that is clearly unrelated to the knowledge base common_types — such as coding exercises, "
    "general trivia, or creative tasks — by responding: "
    "'This question is outside the scope of the knowledge base.'"
)


def build_system_message(system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> ProviderMessage:
    """Return a provider-formatted system message dict.

    Parameters
    ----------
    system_prompt:
        Text content of the system message.  Defaults to
        :data:`DEFAULT_SYSTEM_PROMPT`.

    Returns
    -------
    ProviderMessage
        ``{"role": "system", "content": system_prompt}``
    """
    return {
        "role": MessageRole.SYSTEM.value,
        "content": system_prompt,
    }


def build_chat_messages(
    history: Iterable[Any],
    user_message: Any,
    tool_messages: Iterable[Mapping[str, Any]] | None = None,
) -> list[ProviderMessage]:
    """Assemble a provider-ready message list for a chat-completion request.

    The list always begins with the system message, followed by the
    conversation history, the current user message, and optionally any
    tool-result messages from the current round.

    Both common_types objects (:class:`~app.common_types.models.Message`) and plain dicts
    are accepted anywhere in the sequence — see :func:`_normalize_message`
    for normalisation details.

    Parameters
    ----------
    history:
        Previous messages in the conversation, oldest first.
    user_message:
        The current user message to append after history.
    tool_messages:
        Optional tool-result messages to append at the end of the list
        (used when continuing an agentic loop after tool execution).

    Returns
    -------
    list[ProviderMessage]
        A flat list of normalised provider message dicts ready to pass to
        the chat-completions API.
    """
    messages = [build_system_message()]
    messages.extend(_normalize_messages(history))
    messages.extend(_normalize_messages([user_message]))

    if tool_messages is not None:
        messages.extend(_normalize_messages(tool_messages))

    return messages


def _normalize_messages(messages: Iterable[Any]) -> list[ProviderMessage]:
    """Normalise an iterable of mixed-type messages to provider dicts."""
    return [_normalize_message(message) for message in messages]


def _normalize_message(message: Any) -> ProviderMessage:
    """Coerce a single message — common_types object or dict — to a provider dict.

    Mappings are shallow-copied as-is.  Attribute-based objects (e.g. common_types
    :class:`~app.common_types.models.Message`) are converted by extracting the
    ``role``, ``content``, and optional ``tool_call_id`` / ``name`` /
    ``tool_calls`` attributes.

    Raises
    ------
    TypeError
        If ``role`` is not a recognised string or
        :class:`~app.common_types.enums.MessageRole`, or if ``content`` is not a
        string for non-assistant roles.
    """
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
    """Return a lowercase role string accepted by the provider API.

    Parameters
    ----------
    role:
        Either a :class:`~app.common_types.enums.MessageRole` enum member or a
        plain string.  Strings are stripped and lower-cased before validation.

    Raises
    ------
    TypeError
        If *role* is not a recognised value.
    """
    if isinstance(role, MessageRole):
        return role.value

    if isinstance(role, str):
        normalized_role = role.strip().lower()
        if normalized_role in {"system", "user", "assistant", "tool"}:
            return normalized_role

    raise TypeError(f"Unsupported chat message role: {role!r}")
