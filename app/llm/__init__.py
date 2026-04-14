from app.llm.client import AzureOpenAIChatClient, LLMClientConfigurationError, LLMProviderError, OpenAIChatClient
from app.llm.prompts import DEFAULT_SYSTEM_PROMPT, build_chat_messages, build_system_message
from app.llm.tool_executor import InvalidToolArgumentsError, ToolExecutionContext, ToolExecutor, UnsupportedToolError
from app.llm.tools import get_knowledge_base_tools

__all__ = [
    # Primary name — provider-agnostic
    "OpenAIChatClient",
    # Backward-compatible alias for existing Azure-specific import paths
    "AzureOpenAIChatClient",
    "DEFAULT_SYSTEM_PROMPT",
    "InvalidToolArgumentsError",
    "LLMClientConfigurationError",
    "LLMProviderError",
    "ToolExecutionContext",
    "ToolExecutor",
    "UnsupportedToolError",
    "build_chat_messages",
    "build_system_message",
    "get_knowledge_base_tools",
]
