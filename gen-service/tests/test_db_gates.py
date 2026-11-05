import asyncio
import json

import psycopg
import pytest

from app import db
from app.config import ROOT, settings
from app.validate import validate_sql


def reader_conn():
    return psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user="reader", password=settings.reader_password, connect_timeout=3, autocommit=True,
    )


try:
    reader_conn().close()
    DB_UP = True
except psycopg.Error:
    DB_UP = False

pytestmark = pytest.mark.skipif(not DB_UP, reason="database not reachable")


def test_reader_role_cannot_write():
    with reader_conn() as conn:
        with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
            conn.execute("DELETE FROM rental")


def test_statement_timeout_stops_long_queries():
    with reader_conn() as conn:
        with pytest.raises(psycopg.errors.QueryCanceled):
            conn.execute("SELECT pg_sleep(10)")


def test_cost_gate():
    """Cheap and legitimate queries pass the cost limit; an accidental cross join does not."""
    items = [json.loads(l) for l in (ROOT / "evals" / "dataset.jsonl").read_text().splitlines() if l.strip()]
    references = {i["id"]: validate_sql(i["gold_sql"]) for i in items if i["gold_sql"]}

    async def measure():
        await db.pool.open(wait=True, timeout=10)
        try:
            ref_costs = {k: await db.explain_cost(sql) for k, sql in references.items()}
            cross_join = await db.explain_cost("SELECT count(*) FROM rental, payment")
        finally:
            await db.pool.close()
        return ref_costs, cross_join

    ref_costs, cross_join = asyncio.run(measure())
    too_expensive = {k: round(v) for k, v in ref_costs.items() if v > settings.max_query_cost}
    assert not too_expensive, f"legitimate queries over the cost limit: {too_expensive}"
    assert cross_join > settings.max_query_cost