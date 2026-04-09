from pathlib import Path

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=Path(__file__).resolve().parent.parent / "envs" / ".env",
        env_file_encoding="utf-8",
    )

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    DEBUG: bool
    APP_PORT: PositiveInt
    APP_WORKERS: PositiveInt
    DATABASE_PATH: Path = BASE_DIR / "data" / "qna_rag.sqlite3"
    KNOWLEDGE_DIR: Path | None = None

    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_DEPLOYMENT: str | None = None


settings = Settings()
