"""The core pipeline: question -> SQL -> safety gates -> results, with a self-correcting retry loop."""
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import db
from .config import ROOT, settings
from .llm import generate_sql
from .schema_text import load_schema_text
from .validate import ValidationError, validate_sql

SCHEMA_TEXT = load_schema_text(ROOT / "db" / "schema.json")
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
    confidence: float = 0.0
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
    feedback: list[tuple[str, str]] = []

    for _ in range(MAX_ATTEMPTS):
        generated, usage = await generate_sql(question, SCHEMA_TEXT, feedback)
        res.usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        res.usage["completion_tokens"] += usage.get("completion_tokens", 0)
        res.sql, res.tables_used, res.confidence = generated.sql, generated.tables_used, generated.confidence

        # An empty query means the model declined. Retrying would only pressure it into answering.
        if not generated.sql.strip():
            res.error, res.error_stage = "the model returned no SQL", "validation"
            res.attempts.append(Attempt(sql="", error=res.error, stage=res.error_stage))
            break

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