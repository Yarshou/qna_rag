from pathlib import Path
from typing import Annotated

from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="envs/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    DEBUG: bool
    APP_PORT: PositiveInt
    APP_WORKERS: PositiveInt
    DATABASE_PATH: Path = BASE_DIR / "data" / "qna_rag.sqlite3"
    KNOWLEDGE_DIR: Path | None = None

    MAX_INPUT_LENGTH: PositiveInt = 4_000
    MAX_OUTPUT_LENGTH: PositiveInt = 8_000

    MAX_TOOL_ROUND_TRIPS: PositiveInt = 4

    KNOWLEDGE_MAX_FILE_SIZE_MB: PositiveInt = 10

    HYBRID_ENABLED: bool = True
    EMBEDDING_MODEL: str = "text-embedding-3-small-1"
    EMBEDDING_BATCH_SIZE: PositiveInt = 16
    HYBRID_LEXICAL_WEIGHT: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_DEPLOYMENT: str | None = None

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str | None = None


settings = Settings()
