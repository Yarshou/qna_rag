import asyncio
import logging
from typing import Any

from openai import APIError, AzureOpenAI

from app.config import settings
from app.llm.exceptions import LLMClientConfigurationError, LLMProviderError

logger = logging.getLogger(__name__)


class AzureOpenAIChatClient:
    """Centralized Azure OpenAI chat-completions wrapper."""

    def __init__(self) -> None:
        if settings.AZURE_OPENAI_API_KEY is None:
            raise LLMClientConfigurationError("AZURE_OPENAI_API_KEY is required.")
        if not settings.AZURE_OPENAI_ENDPOINT:
            raise LLMClientConfigurationError("AZURE_OPENAI_ENDPOINT is required.")
        if not settings.OPENAI_API_VERSION:
            raise LLMClientConfigurationError("OPENAI_API_VERSION is required.")
        if not settings.AZURE_OPENAI_DEPLOYMENT:
            raise LLMClientConfigurationError("AZURE_OPENAI_DEPLOYMENT is required.")

        self._deployment = settings.AZURE_OPENAI_DEPLOYMENT
        self._client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY.get_secret_value(),
            api_version=settings.OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> Any:
        """Execute a synchronous chat completion request against Azure OpenAI."""
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
        except APIError as exc:
            logger.error(
                "azure_openai_chat_completion_failed",
                extra={"deployment": self._deployment, "error_type": exc.__class__.__name__},
            )
            raise LLMProviderError("Azure OpenAI chat completion failed.") from exc
        except Exception as exc:
            logger.error(
                "azure_openai_chat_completion_unexpected_failure",
                extra={"deployment": self._deployment, "error_type": exc.__class__.__name__},
            )
            raise LLMProviderError("Unexpected Azure OpenAI client failure.") from exc

        logger.info(
            "azure_openai_chat_completion_succeeded",
            extra={
                "deployment": self._deployment,
                "choices": len(getattr(response, "choices", [])),
                "used_tools": tools is not None,
            },
        )
        return response

    async def create_chat_completion_async(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> Any:
        """Execute the synchronous SDK call in a worker thread for async service code."""
        return await asyncio.to_thread(
            self.create_chat_completion,
            messages,
            tools,
            tool_choice,
        )

    @staticmethod
    def extract_first_message(response: Any) -> Any:
        """Return the first provider message from a chat completion response."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMProviderError("Azure OpenAI response did not include any choices.")

        message = getattr(choices[0], "message", None)
        if message is None:
            raise LLMProviderError("Azure OpenAI response choice did not include a message.")

        return message

    @staticmethod
    def has_tool_calls(response: Any) -> bool:
        """Return True when the first response message includes tool calls."""
        message = AzureOpenAIChatClient.extract_first_message(response)
        return bool(getattr(message, "tool_calls", None))
