"""For each benchmark question: does retrieval (top-k plus join paths) include every table the reference SQL uses?
Costs no LLM tokens. Used to choose retrieval_top_k."""
import json
import sys
from pathlib import Path

import psycopg
import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen-service"))
from app.config import settings  # noqa: E402
from app.retrieval import embed_query  # noqa: E402
from app.schema_text import CATALOG  # noqa: E402


def gold_tables(sql: str) -> set[str]:
    tree = sqlglot.parse_one(sql, read="postgres")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return {t.name.lower() for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in ctes}


def main():
    items = [json.loads(l) for l in (ROOT / "evals" / "dataset.jsonl").read_text().splitlines() if l.strip()]
    items = [i for i in items if i["gold_sql"]]
    vectors = {i["id"]: embed_query(i["question"]) for i in items}

    with psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user="app_user", password=settings.app_user_password,
    ) as conn:
        for k in range(2, 9):
            hits, sizes, misses = 0, [], []
            for item in items:
                rows = conn.execute(
                    "SELECT table_name FROM app.schema_index ORDER BY embedding <=> %s::vector LIMIT %s",
                    (vectors[item["id"]], k),
                ).fetchall()
                selected = CATALOG.connect([r[0] for r in rows])
                needed = gold_tables(item["gold_sql"])
                sizes.append(len(selected))
                if needed <= selected:
                    hits += 1
                else:
                    misses.append(f"  {item['id']}: missing {sorted(needed - selected)}")
            marker = "  <- current setting" if k == settings.retrieval_top_k else ""
            print(f"k={k}: all needed tables found for {hits}/{len(items)} ({100 * hits / len(items):.0f}%), "
                  f"avg {sum(sizes) / len(sizes):.1f} of {len(CATALOG.table_names)} tables{marker}")
            if k == settings.retrieval_top_k and misses:
                print("\n".join(misses))


if __name__ == "__main__":
    main()