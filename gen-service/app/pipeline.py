"""The core pipeline: intent check -> prompt context -> SQL or refusal -> safety gates -> results,
with a self-correcting retry loop."""
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import db
from .config import settings
from .guard import check_intent
from .llm import generate_sql
from .prompt import build_system_prompt
from .retrieval import build_context
from .validate import ValidationError, validate_sql

MAX_ATTEMPTS = 3  # the first try plus up to 2 corrections


class StageError(Exception):
    """A failure at one stage of the pipeline: validation, cost or execution."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


@dataclass
class Attempt:
    sql: str
    error: str | None = None
    stage: str | None = None


@dataclass
class PipelineResult:
    question: str
    sql: str = ""
    tables_used: list[str] = field(default_factory=list)
    schema_tables: list[str] = field(default_factory=list)
    terms_used: list[str] = field(default_factory=list)
    examples_used: list[str] = field(default_factory=list)
    confidence: float = 0.0
    refused: bool = False
    refusal_category: str | None = None
    refusal_reason: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    error_stage: str | None = None
    query_cost: float | None = None
    attempts: list[Attempt] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


async def _gate_and_execute(raw_sql: str):
    """Run one query through every safety gate, then execute it. Raises StageError on failure."""
    try:
        sql = validate_sql(raw_sql)
    except ValidationError as exc:
        raise StageError("validation", f"rejected by validation: {exc}") from exc
    try:
        cost = await db.explain_cost(sql)
    except psycopg.Error as exc:
        raise StageError("execution", str(exc).strip()) from exc
    if cost > settings.max_query_cost:
        raise StageError(
            "cost",
            f"query too expensive (estimated cost {cost:,.0f} exceeds limit {settings.max_query_cost:,.0f})",
        )
    try:
        columns, rows, truncated = await db.run_query(sql)
    except psycopg.Error as exc:
        raise StageError("execution", str(exc).strip()) from exc
    return sql, cost, columns, rows, truncated


async def answer(question: str) -> PipelineResult:
    res = PipelineResult(question=question)

    # 1. Deterministic check: requests to change data are refused before any LLM call.
    blocked = check_intent(question)
    if blocked:
        res.refused = True
        res.refusal_category, res.refusal_reason = blocked
        return res

    # 2. Build the prompt context: relevant tables, business definitions, similar examples.
    context = await build_context(question)
    res.schema_tables = context.tables
    res.terms_used = [t["name"] for t in context.terms]
    res.examples_used = [e["question"] for e in context.examples]
    system_prompt = build_system_prompt(context)
    feedback: list[tuple[str, str]] = []

    for _ in range(MAX_ATTEMPTS):
        generated, usage = await generate_sql(question, system_prompt, feedback)
        res.usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        res.usage["completion_tokens"] += usage.get("completion_tokens", 0)
        res.tables_used, res.confidence = generated.tables_used, generated.confidence

        # 3. The model judged the question unanswerable, or produced no usable query: refuse, never guess.
        if not generated.answerable or not generated.sql.strip():
            res.refused = True
            res.refusal_category = generated.refusal_category or "unclear"
            res.refusal_reason = generated.refusal_reason or "This question can't be answered from this database."
            res.sql, res.error, res.error_stage = "", None, None
            res.attempts.append(Attempt(sql="", error=res.refusal_reason, stage="refusal"))
            break

        # 4. Safety gates and execution, with self-correction on failure.
        res.sql = generated.sql
        try:
            res.sql, res.query_cost, res.columns, res.rows, res.truncated = await _gate_and_execute(generated.sql)
            res.error = res.error_stage = None
            res.attempts.append(Attempt(sql=res.sql))
            break
        except StageError as exc:
            res.error, res.error_stage = str(exc), exc.stage
            res.attempts.append(Attempt(sql=generated.sql, error=res.error, stage=exc.stage))
            feedback.append((generated.sql, res.error))

    return res