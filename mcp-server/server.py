"""MCP server: lets AI assistants (Claude Desktop, Cursor, ...) query the rental database through the
text-to-SQL engine.

It is a thin client of the generation service, so every safety layer, the cache, the daily budget,
the request log and tracing apply to assistant traffic exactly as they do to the web app.
Never print() in this file: over stdio, stdout carries the protocol itself."""
import os
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEN_SERVICE_URL = os.getenv("GEN_SERVICE_URL", "http://localhost:8000")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
MAX_ROWS_FOR_ASSISTANT = 50  # keeps tool results small enough for an assistant's context window

mcp = MCPServer(
    "text-to-sql",
    instructions=(
        "Answers questions about a DVD rental business's database (films, rentals, payments, customers, "
        "stores). Read-only: requests to change data are refused. Call describe_database or "
        "list_business_terms first if unsure what can be asked."
    ),
    version="1.0.0",
)


def shape_result(r: dict) -> dict:
    """Turn a generation-service response into a compact result an assistant can read."""
    if r.get("refused"):
        return {"status": "refused", "category": r.get("refusal_category"), "reason": r.get("refusal_reason")}
    if r.get("error"):
        return {"status": "error", "stage": r.get("error_stage"), "error": r.get("error"), "sql": r.get("sql")}
    rows = r.get("rows", [])
    return {
        "status": "ok",
        "sql": r.get("sql", ""),
        "columns": r.get("columns", []),
        "rows": rows[:MAX_ROWS_FOR_ASSISTANT],
        "row_count": r.get("row_count", len(rows)),
        "truncated": bool(r.get("truncated")) or len(rows) > MAX_ROWS_FOR_ASSISTANT,
        "business_definitions_used": r.get("terms_used", []),
        "cached": r.get("cache_hit", False),
    }


@mcp.tool()
async def ask_database(question: str) -> dict:
    """Answer a plain-English question about the DVD rental business (films, actors, categories,
    rentals, payments, customers, stores, staff) by generating and running a read-only SQL query.

    Returns the SQL, the column names and up to 50 rows. Requests to change data are refused,
    and questions the data cannot answer return a refusal with a reason."""
    headers = {"x-internal-token": INTERNAL_API_TOKEN} if INTERNAL_API_TOKEN else {}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{GEN_SERVICE_URL}/generate", json={"question": question}, headers=headers)
    except httpx.HTTPError as exc:
        raise ToolError(f"The query service is unreachable: {exc}") from exc

    if resp.status_code == 422:
        raise ToolError("The question must be between 3 and 500 characters.")
    if resp.status_code == 429:
        raise ToolError(resp.json().get("detail", "A rate or daily limit was reached; try again later."))
    if resp.status_code != 200:
        raise ToolError(f"The query service failed (HTTP {resp.status_code}).")
    return shape_result(resp.json())


@mcp.tool()
async def describe_database() -> str:
    """Describe the tables in the DVD rental database and what each one contains,
    so you know which questions it can answer."""
    tables = yaml.safe_load((ROOT / "db" / "schema_docs.yaml").read_text())["tables"]
    return "\n".join(f"- {name}: {(info or {}).get('description', '')}" for name, info in sorted(tables.items()))


@mcp.tool()
async def list_business_terms() -> list[dict]:
    """List the company's business terms (for example 'VIP customer' or 'churned customer') with
    their exact definitions. Questions that use these terms are answered with these definitions."""
    terms = yaml.safe_load((ROOT / "db" / "semantic_layer.yaml").read_text())["terms"]
    return [{"term": t["name"], "synonyms": t.get("synonyms", []), "definition": t["definition"]} for t in terms]


if __name__ == "__main__":
    mcp.run(transport="stdio")