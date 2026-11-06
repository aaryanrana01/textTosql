from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]   # app/ -> gen-service/ -> project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Database
    postgres_db: str
    reader_password: str
    app_user_password: str
    db_host: str = "localhost"
    db_port: int = 5432
    db_sslmode: str = "prefer"   # "require" on hosted databases such as Neon, which accept only SSL

    # LLM
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_reasoning_effort: str | None = None

    # Safety gates
    max_limit: int = 1000              # LIMIT added to queries that have none
    max_query_cost: float = 1_000_000  # EXPLAIN cost above which a query is rejected

    # Schema retrieval
    schema_retrieval: bool = True   # False = send every table (for comparison runs)
    retrieval_top_k: int = 4        # tables retrieved before join-path expansion
    few_shot_k: int = 3             # similar worked examples per prompt; 0 turns them off

    # Protection for the deployed service
    internal_api_token: str = ""   # when set, /generate requires it in the X-Internal-Token header
    daily_token_budget: int = 0    # stop answering once this many LLM tokens were used today (0 = no limit)

    # Answer cache
    redis_url: str = ""                # empty disables caching (tests, CI)
    cache_ttl_seconds: int = 86_400    # cached SQL is reused for up to 24 hours

    # Tracing (optional): all three must be set for tracing to turn on
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


settings = Settings()