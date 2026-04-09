__all__ = [
    "UnsupportedToolError",
    "InvalidToolArgumentsError",
    "LLMClientConfigurationError",
    "LLMProviderError",
]


class UnsupportedToolError(ValueError):
    """Raised when the model requests a tool that the executor does not expose."""


class InvalidToolArgumentsError(ValueError):
    """Raised when a tool call contains malformed or unsupported arguments."""


class LLMClientConfigurationError(RuntimeError):
    """Raised when required Azure OpenAI settings are missing."""


class LLMProviderError(RuntimeError):
    """Raised when the Azure OpenAI provider call fails."""
