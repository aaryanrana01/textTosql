"""Everything the model sees: fixed rules, the relevant schema, matching business definitions and similar worked examples."""
from dataclasses import dataclass, field

RULES = """You are an expert PostgreSQL analyst.
Write ONE read-only PostgreSQL SELECT query that answers the user's question.

Rules:
- Use only the tables and columns listed in the schema below.
- Use the simplest query that answers the question. Do not join tables that are not needed.
- Join tables using the foreign keys shown with ->.
- Use only the allowed values shown in parentheses for enum columns.
- If the question uses a term listed under business definitions, apply that definition exactly.
- Respond with JSON only, in exactly this shape:
  {"sql": "<the query>", "tables_used": ["<table>", ...], "confidence": <number from 0 to 1>}"""


@dataclass
class PromptContext:
    schema_text: str
    tables: list[str] = field(default_factory=list)
    terms: list[dict] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)


def build_system_prompt(ctx: PromptContext) -> str:
    parts = [RULES, "Schema:\n" + ctx.schema_text]
    if ctx.terms:
        lines = [f"- {t['name']}: {t['definition']} (SQL: {t['sql']})" for t in ctx.terms]
        parts.append("Business definitions:\n" + "\n".join(lines))
    if ctx.examples:
        shots = [f"Question: {e['question']}\nSQL: {e['sql']}" for e in ctx.examples]
        parts.append(
            "Examples of correct queries on this database (patterns to follow, not answers to copy):\n\n"
            + "\n\n".join(shots)
        )
    return "\n\n".join(parts)
