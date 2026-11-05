"""Embed each table's description into pgvector so the service can retrieve relevant tables.
Re-run whenever db/schema_docs.yaml or db/schema.json changes."""
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen-service"))
from app.config import settings  # noqa: E402
from app.retrieval import EMBED_DIM, get_model, to_vector_literal  # noqa: E402
from app.schema_text import CATALOG  # noqa: E402

DDL = f"""
CREATE TABLE IF NOT EXISTS app.schema_index (
    table_name text PRIMARY KEY,
    content    text NOT NULL,
    embedding  vector({EMBED_DIM}) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
)"""


def main():
    names = CATALOG.table_names
    documents = [CATALOG.document(n) for n in names]
    vectors = list(get_model().passage_embed(documents))

    with psycopg.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user="app_user", password=settings.app_user_password,
    ) as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE app.schema_index")
        for name, doc, vec in zip(names, documents, vectors):
            conn.execute(
                "INSERT INTO app.schema_index (table_name, content, embedding) VALUES (%s, %s, %s::vector)",
                (name, doc, to_vector_literal(vec)),
            )
    print(f"Indexed {len(names)} tables into app.schema_index")


if __name__ == "__main__":
    main()