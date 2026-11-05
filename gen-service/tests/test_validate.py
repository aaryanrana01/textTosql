import json

import pytest

from app.config import ROOT, settings
from app.validate import ValidationError, validate_sql

ALLOWED = [
    "SELECT count(*) FROM film",
    "SELECT title FROM film WHERE rating = 'R' LIMIT 5",
    "WITH t AS (SELECT customer_id, sum(amount) AS total FROM payment GROUP BY customer_id) SELECT count(*) FROM t",
    "SELECT title FROM film UNION SELECT name FROM category",
    "SELECT rating, avg(length) OVER (PARTITION BY rating) FROM film",
    "SELECT f.title FROM film f WHERE NOT EXISTS (SELECT 1 FROM inventory i WHERE i.film_id = f.film_id)",
    "SELECT count(*) FROM public.film",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allows_safe_reads(sql):
    validate_sql(sql)


def test_adds_limit_when_missing():
    assert f"LIMIT {settings.max_limit}" in validate_sql("SELECT title FROM film")


def test_keeps_existing_limit():
    out = validate_sql("SELECT title FROM film LIMIT 5")
    assert "LIMIT 5" in out and f"LIMIT {settings.max_limit}" not in out


BLOCKED = {
    "delete": "DELETE FROM rental",
    "update": "UPDATE film SET rental_rate = 0.99",
    "insert": "INSERT INTO category (name) VALUES ('x')",
    "drop": "DROP TABLE customer",
    "truncate": "TRUNCATE rental",
    "stacked statements": "SELECT 1; DROP TABLE film",
    "write hidden in CTE": "WITH d AS (DELETE FROM rental RETURNING *) SELECT count(*) FROM d",
    "select into": "SELECT * INTO film_copy FROM film",
    "row locking": "SELECT * FROM film FOR UPDATE",
    "sleep": "SELECT pg_sleep(10)",
    "file read": "SELECT pg_read_file('/etc/passwd')",
    "system catalog": "SELECT * FROM pg_catalog.pg_roles",
    "information schema": "SELECT * FROM information_schema.tables",
    "unknown table": "SELECT * FROM users",
    "change settings": "SELECT set_config('statement_timeout', '0', false)",
    "set statement": "SET statement_timeout = 0",
    "grant": "GRANT ALL ON film TO public",
    "not sql": "this is not sql at all",
    "empty": "",
}


@pytest.mark.parametrize("sql", list(BLOCKED.values()), ids=list(BLOCKED.keys()))
def test_blocks_unsafe_sql(sql):
    with pytest.raises(ValidationError):
        validate_sql(sql)


def _reference_items():
    path = ROOT / "evals" / "dataset.jsonl"
    items = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [i for i in items if i["gold_sql"]]


@pytest.mark.parametrize("item", _reference_items(), ids=lambda i: i["id"])
def test_reference_queries_pass_validation(item):
    validate_sql(item["gold_sql"])