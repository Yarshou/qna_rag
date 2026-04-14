from pathlib import Path

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
    )

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    DEBUG: bool
    APP_PORT: PositiveInt
    APP_WORKERS: PositiveInt
    DATABASE_PATH: Path = BASE_DIR / "data" / "qna_rag.sqlite3"
    KNOWLEDGE_DIR: Path | None = None

    # ── Guardrail limits ──────────────────────────────────────────────────────
    # Hard character limits for user input and assistant output.
    MAX_INPUT_LENGTH: PositiveInt = 4_000
    MAX_OUTPUT_LENGTH: PositiveInt = 8_000

    # ── Agent flow limits ─────────────────────────────────────────────────────
    # Maximum LLM ↔ tool round-trips before the flow is terminated.
    MAX_TOOL_ROUND_TRIPS: PositiveInt = 4

    # ── Knowledge base limits ─────────────────────────────────────────────────
    # Files larger than this threshold are skipped during KB indexing.
    KNOWLEDGE_MAX_FILE_SIZE_MB: PositiveInt = 10

    # Azure OpenAI provider (active when AZURE_OPENAI_ENDPOINT is set)
    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_DEPLOYMENT: str | None = None

    # Generic OpenAI-compatible provider: OpenRouter, DIAL, Ollama, etc.
    # Active when OPENAI_BASE_URL is set and AZURE_OPENAI_ENDPOINT is not.
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str | None = None


settings = Settings()
