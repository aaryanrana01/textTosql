from decimal import Decimal
from typing import Any

from psycopg_pool import AsyncConnectionPool

from .config import settings

MAX_ROWS = 200

pool = AsyncConnectionPool(
    conninfo=(
        f"host={settings.db_host} port={settings.db_port} dbname={settings.postgres_db} "
        f"user=reader password={settings.reader_password}"
    ),
    min_size=1,
    max_size=5,
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