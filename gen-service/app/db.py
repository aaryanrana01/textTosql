import json
import logging
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .config import settings

logger = logging.getLogger(__name__)

MAX_ROWS = 200


def _conninfo(user: str, password: str) -> str:
    """Connection settings for one database role. sslmode comes from settings:
    'prefer' locally (Docker has no SSL), 'require' on hosted databases such as Neon."""
    return (
        f"host={settings.db_host} port={settings.db_port} dbname={settings.postgres_db} "
        f"sslmode={settings.db_sslmode} user={user} password={password}"
    )


# Runs generated SQL as the read-only reader role.
pool = AsyncConnectionPool(
    conninfo=_conninfo("reader", settings.reader_password),
    min_size=1,
    max_size=5,
    open=False,
)

# A separate, small pool for the app_user role, which can write logs but never runs generated SQL.
app_pool = AsyncConnectionPool(
    conninfo=_conninfo("app_user", settings.app_user_password),
    min_size=1,
    max_size=2,
    open=False,
)


def _clean(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


async def run_query(sql: str) -> tuple[list[str], list[list[Any]], bool]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            columns = [d.name for d in cur.description] if cur.description else []
            raw_rows = await cur.fetchmany(MAX_ROWS + 1)
    truncated = len(raw_rows) > MAX_ROWS
    rows = [[_clean(v) for v in row] for row in raw_rows[:MAX_ROWS]]
    return columns, rows, truncated


async def explain_cost(sql: str) -> float:
    """Postgres's estimated cost for a query, without running it."""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"EXPLAIN (FORMAT JSON) {sql}")
            row = await cur.fetchone()
    plan = row[0] if not isinstance(row[0], str) else json.loads(row[0])
    return float(plan[0]["Plan"]["Total Cost"])


LOG_FIELDS = (
    "question", "final_sql", "status", "error_stage", "error", "attempts", "attempt_errors",
    "row_count", "truncated", "query_cost", "latency_ms", "prompt_tokens", "completion_tokens", "model",
    "cache_hit",
)
LOG_SQL = (
    f"INSERT INTO app.request_log ({', '.join(LOG_FIELDS)}) "
    f"VALUES ({', '.join(f'%({f})s' for f in LOG_FIELDS)})"
)


async def log_request(entry: dict) -> None:
    """Record one request. Logging must never break a user's request, so failures are only warned about."""
    params = {f: entry.get(f) for f in LOG_FIELDS}
    params["attempt_errors"] = Jsonb(params["attempt_errors"] or [])
    params["cache_hit"] = bool(params["cache_hit"])  # the column is NOT NULL; failed requests never hit the cache
    try:
        async with app_pool.connection() as conn:
            await conn.execute(LOG_SQL, params)
    except Exception as exc:
        logger.warning("could not write request log: %s", exc)


async def tokens_used_today() -> int:
    """LLM tokens used since midnight (database time, UTC), from the request log."""
    async with app_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT coalesce(sum(coalesce(prompt_tokens, 0) + coalesce(completion_tokens, 0)), 0) "
            "FROM app.request_log WHERE created_at >= date_trunc('day', now())"
        )
        row = await cur.fetchone()
    return int(row[0])