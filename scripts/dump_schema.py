"""Dump the Pagila schema (tables, columns, keys, enum values) to db/schema.json."""
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EXCLUDED_TABLES = {"film_embedding"}

TABLES_SQL = """
SELECT c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND NOT c.relispartition
ORDER BY 1;
"""

COLUMNS_SQL = """
SELECT column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = %s
ORDER BY ordinal_position;
"""

ENUM_SQL = """
SELECT e.enumlabel
FROM pg_type t
JOIN pg_enum e ON e.enumtypid = t.oid
WHERE t.typname = %s
ORDER BY e.enumsortorder;
"""

KEYS_SQL = """
SELECT con.contype, a.attname, rc.relname, ra.attname
FROM pg_constraint con
CROSS JOIN LATERAL unnest(con.conkey, con.confkey) AS k(col, refcol)
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.col
LEFT JOIN pg_class rc ON rc.oid = con.confrelid
LEFT JOIN pg_attribute ra ON ra.attrelid = con.confrelid AND ra.attnum = k.refcol
WHERE con.conrelid = %s::regclass
  AND con.contype IN ('p', 'f');
"""


def column_type(data_type: str, udt_name: str) -> str:
    if data_type == "USER-DEFINED":
        return udt_name                      # e.g. mpaa_rating
    if data_type == "ARRAY":
        return udt_name.lstrip("_") + "[]"   # e.g. _text -> text[]
    return data_type


def main() -> None:
    schema = {}
    with psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user="reader",
        password=os.environ["READER_PASSWORD"],
    ) as conn, conn.cursor() as cur:
        cur.execute(TABLES_SQL)
        tables = [row[0] for row in cur.fetchall() if row[0] not in EXCLUDED_TABLES]

        for table in tables:
            cur.execute(COLUMNS_SQL, (table,))
            columns = []
            for name, data_type, udt_name, nullable in cur.fetchall():
                col = {
                    "name": name,
                    "type": column_type(data_type, udt_name),
                    "nullable": nullable == "YES",
                }
                if data_type == "USER-DEFINED":
                    cur.execute(ENUM_SQL, (udt_name,))
                    values = [row[0] for row in cur.fetchall()]
                    if values:
                        col["allowed_values"] = values
                columns.append(col)

            cur.execute(KEYS_SQL, (f"public.{table}",))
            primary_key, foreign_keys = [], []
            for contype, column, ref_table, ref_column in cur.fetchall():
                if contype == "p":
                    primary_key.append(column)
                else:
                    foreign_keys.append(
                        {"column": column, "ref_table": ref_table, "ref_column": ref_column}
                    )

            schema[table] = {
                "columns": columns,
                "primary_key": primary_key,
                "foreign_keys": foreign_keys,
            }

    out = ROOT / "db" / "schema.json"
    out.write_text(json.dumps(schema, indent=2))
    print(f"Wrote {len(schema)} tables to {out}")


if __name__ == "__main__":
    main()