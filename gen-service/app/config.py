from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]   # app/ -> gen-service/ -> project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Database
    postgres_db: str
    reader_password: str
    db_host: str = "localhost"
    db_port: int = 5432

    # LLM
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_reasoning_effort: str | None = None


settings = Settings()