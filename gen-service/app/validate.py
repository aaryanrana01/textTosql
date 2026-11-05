"""SQL safety gates: every generated query passes through validate_sql before it reaches the database."""
import json

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from .config import ROOT, settings

# The only tables generated SQL may touch: the same 15 the model sees in its prompt.
ALLOWED_TABLES = {name.lower() for name in json.loads((ROOT / "db" / "schema.json").read_text())}

# Statement types allowed at the top level of a query.
ALLOWED_ROOTS = tuple(getattr(exp, n) for n in ("Select", "Union", "Intersect", "Except") if hasattr(exp, n))

# Operations that must not appear anywhere in the query, including inside CTEs and subqueries.
FORBIDDEN_NODES = tuple(
    getattr(exp, n)
    for n in (
        "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
        "TruncateTable", "Command", "Into", "Lock", "Grant", "Copy", "Set",
        "Transaction", "Commit", "Rollback", "Use",
    )
    if hasattr(exp, n)
)

# Functions that can sleep, read server files, reach other databases or change settings.
BLOCKED_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "dblink", "dblink_exec",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "set_config",
}


class ValidationError(Exception):
    """Raised when generated SQL fails a safety gate."""


def _function_names(tree: exp.Expression):
    for node in tree.find_all(exp.Func):
        yield (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def validate_sql(sql: str) -> str:
    """Return a safe, normalized version of the query, or raise ValidationError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as exc:
        raise ValidationError(f"could not parse SQL: {exc}") from exc

    # Gate 1: exactly one statement, so "SELECT 1; DROP TABLE film" can't sneak through.
    if not statements:
        raise ValidationError("the model returned no SQL")
    if len(statements) > 1:
        raise ValidationError("exactly one statement is allowed")
    tree = statements[0]

    # Gate 2: the statement itself must be a read query.
    if not isinstance(tree, ALLOWED_ROOTS):
        raise ValidationError(f"only SELECT queries are allowed, got {tree.key.upper()}")

    # Gate 3: no writes, DDL, locking or SELECT INTO hidden anywhere inside it.
    forbidden = tree.find(*FORBIDDEN_NODES)
    if forbidden is not None:
        raise ValidationError(f"forbidden operation: {forbidden.key.upper()}")

    # Gate 4: no dangerous functions.
    for name in _function_names(tree):
        if name in BLOCKED_FUNCTIONS:
            raise ValidationError(f"function not allowed: {name}")

    # Gate 5: only the allowed tables (or the query's own CTE names), only in the public schema.
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:  # table functions such as generate_series()
            continue
        if table.db and table.db.lower() != "public":
            raise ValidationError(f"schema not allowed: {table.db}")
        if name not in ALLOWED_TABLES and name not in cte_names:
            raise ValidationError(f"table not allowed: {name}")

    # Gate 6: cap the result size if the query doesn't already have a LIMIT.
    if not tree.args.get("limit"):
        tree = tree.limit(settings.max_limit)

    return tree.sql(dialect="postgres")