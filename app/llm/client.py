import asyncio
import logging
from typing import Any

from openai import APIError, AzureOpenAI, OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolParam,
)

from app.config import settings
from app.llm.exceptions import LLMClientConfigurationError, LLMProviderError

logger = logging.getLogger(__name__)


class OpenAIChatClient:
    """Unified chat-completions client for Azure OpenAI and generic
    OpenAI-compatible providers (OpenRouter, DIAL, Ollama, etc.).

    Provider selection is automatic based on which environment variables are set:

    Azure OpenAI mode (AZURE_OPENAI_ENDPOINT is set):
        AZURE_OPENAI_API_KEY   — API key for the Azure resource
        AZURE_OPENAI_ENDPOINT  — Azure resource base URL
        OPENAI_API_VERSION     — API version string (e.g. 2024-02-15-preview)
        AZURE_OPENAI_DEPLOYMENT — Deployment / model name

    Generic OpenAI-compatible mode (OPENAI_BASE_URL is set):
        OPENAI_API_KEY  — API key (provider-issued; use "ollama" for local Ollama)
        OPENAI_BASE_URL — Provider base URL (e.g. https://openrouter.ai/api/v1)
        OPENAI_MODEL    — Model identifier (e.g. meta-llama/llama-3-8b-instruct)

    Azure mode takes precedence when both endpoint groups are configured.
    """

    def __init__(self) -> None:
        if settings.AZURE_OPENAI_ENDPOINT:
            self._client, self._model = self._build_azure_client()
            self._provider = "azure"
        elif settings.OPENAI_BASE_URL:
            self._client, self._model = self._build_generic_client()
            self._provider = "generic"
        else:
            raise LLMClientConfigurationError(
                "No LLM provider configured. "
                "Set AZURE_OPENAI_ENDPOINT for Azure OpenAI, "
                "or OPENAI_BASE_URL for a generic OpenAI-compatible provider "
                "(OpenRouter, DIAL, Ollama, etc.)."
            )

    @staticmethod
    def _build_azure_client() -> tuple[AzureOpenAI, str]:
        if settings.AZURE_OPENAI_API_KEY is None:
            raise LLMClientConfigurationError("AZURE_OPENAI_API_KEY is required for Azure OpenAI.")
        if not settings.OPENAI_API_VERSION:
            raise LLMClientConfigurationError("OPENAI_API_VERSION is required for Azure OpenAI.")
        if not settings.AZURE_OPENAI_DEPLOYMENT:
            raise LLMClientConfigurationError("AZURE_OPENAI_DEPLOYMENT is required for Azure OpenAI.")

        client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY.get_secret_value(),
            api_version=settings.OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )
        return client, settings.AZURE_OPENAI_DEPLOYMENT

    @staticmethod
    def _build_generic_client() -> tuple[OpenAI, str]:
        if settings.OPENAI_API_KEY is None:
            raise LLMClientConfigurationError("OPENAI_API_KEY is required for generic OpenAI-compatible providers.")
        if not settings.OPENAI_MODEL:
            raise LLMClientConfigurationError("OPENAI_MODEL is required for generic OpenAI-compatible providers.")

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            base_url=settings.OPENAI_BASE_URL,
        )
        return client, settings.OPENAI_MODEL

    def create_chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam] | None = None,
        tool_choice: ChatCompletionToolChoiceOptionParam = "auto",
    ) -> ChatCompletion:
        """Execute a synchronous chat completion request against the configured provider."""
        try:
            response: ChatCompletion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
        except APIError as exc:
            logger.error(
                "llm_chat_completion_failed",
                extra={"provider": self._provider, "model": self._model, "error_type": exc.__class__.__name__},
            )
            raise LLMProviderError("LLM chat completion request failed.") from exc
        except Exception as exc:
            logger.error(
                "llm_chat_completion_unexpected_failure",
                extra={"provider": self._provider, "model": self._model, "error_type": exc.__class__.__name__},
            )
            raise LLMProviderError("Unexpected LLM client failure.") from exc

        logger.info(
            "llm_chat_completion_succeeded",
            extra={
                "provider": self._provider,
                "model": self._model,
                "choices": len(getattr(response, "choices", [])),
                "used_tools": tools is not None,
            },
        )
        return response

    async def create_chat_completion_async(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam] | None = None,
        tool_choice: ChatCompletionToolChoiceOptionParam = "auto",
    ) -> ChatCompletion:
        """Run the synchronous SDK call in a worker thread for use in async service code."""
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
            raise LLMProviderError("LLM response did not include any choices.")

        message = getattr(choices[0], "message", None)
        if message is None:
            raise LLMProviderError("LLM response choice did not include a message.")

        return message

    @staticmethod
    def has_tool_calls(response: Any) -> bool:
        """Return True when the first response message includes tool calls."""
        message = OpenAIChatClient.extract_first_message(response)
        return bool(getattr(message, "tool_calls", None))


# Backward-compatible alias — code that imports AzureOpenAIChatClient keeps working.
AzureOpenAIChatClient = OpenAIChatClient
