"""Build the pgvector indexes used for prompt context:
- app.schema_index: one row per table (from db/schema_docs.yaml) for schema retrieval
- app.example_index: one row per worked example (from db/examples.jsonl) for few-shot retrieval
Re-run whenever those files or db/schema.json change."""
import json
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen-service"))
from app.config import settings  # noqa: E402
from app.retrieval import EMBED_DIM, get_model, to_vector_literal  # noqa: E402
from app.schema_text import CATALOG  # noqa: E402

SCHEMA_DDL = f"""
CREATE TABLE IF NOT EXISTS app.schema_index (
    table_name text PRIMARY KEY,
    content    text NOT NULL,
    embedding  vector({EMBED_DIM}) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
)"""

EXAMPLES_DDL = f"""
CREATE TABLE IF NOT EXISTS app.example_index (
    id         text PRIMARY KEY,
    question   text NOT NULL,
    sql        text NOT NULL,
    embedding  vector({EMBED_DIM}) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
)"""


def main():
    model = get_model()
    names = CATALOG.table_names
    documents = [CATALOG.document(n) for n in names]
    table_vectors = list(model.passage_embed(documents))

    examples = [json.loads(l) for l in (ROOT / "db" / "examples.jsonl").read_text().splitlines() if l.strip()]
    # Examples are matched question-to-question, so both sides use query embeddings.
    example_vectors = list(model.query_embed([e["question"] for e in examples]))

    with psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user="app_user", password=settings.app_user_password,
    ) as conn:
        conn.execute(SCHEMA_DDL)
        conn.execute("TRUNCATE app.schema_index")
        for name, doc, vec in zip(names, documents, table_vectors):
            conn.execute(
                "INSERT INTO app.schema_index (table_name, content, embedding) VALUES (%s, %s, %s::vector)",
                (name, doc, to_vector_literal(vec)),
            )
        conn.execute(EXAMPLES_DDL)
        conn.execute("TRUNCATE app.example_index")
        for ex, vec in zip(examples, example_vectors):
            conn.execute(
                "INSERT INTO app.example_index (id, question, sql, embedding) VALUES (%s, %s, %s, %s::vector)",
                (ex["id"], ex["question"], ex["sql"], to_vector_literal(vec)),
            )
    print(f"Indexed {len(names)} tables and {len(examples)} examples")


if __name__ == "__main__":
    main()
