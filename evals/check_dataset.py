"""Run every reference query in the dataset and flag problems before any evaluation."""
import json
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen-service"))
from app.config import settings  # noqa: E402

items = [json.loads(line) for line in (ROOT / "evals" / "dataset.jsonl").read_text().splitlines() if line.strip()]

problems = 0
with psycopg.connect(
    host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
    user="reader", password=settings.reader_password, autocommit=True,
) as conn:
    for item in items:
        if item["expect"] == "refuse":
            print(f"{item['id']}  (should refuse)  {item['question']}")
            continue
        try:
            rows = conn.execute(item["gold_sql"]).fetchall()
        except psycopg.Error as exc:
            problems += 1
            print(f"{item['id']}  ERROR  {str(exc).strip()[:150]}")
            continue
        flag = ""
        if not rows:
            flag = "EMPTY"
        elif len(rows) == 1 and all(v is None for v in rows[0]):
            flag = "NULL RESULT"
        elif len(rows) > 200:
            flag = "OVER 200 ROWS"
        if flag:
            problems += 1
        print(f"{item['id']}  {len(rows):>4} rows  {flag:<13} first row: {rows[0] if rows else None}")

answerable = sum(1 for i in items if i["expect"] == "answer")
print(f"\n{len(items)} items ({answerable} answerable, {len(items) - answerable} refuse), {problems} problems")