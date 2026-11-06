"""The core pipeline: intent check -> cache -> prompt context -> SQL or refusal -> safety gates -> results,
with a self-correcting retry loop. Each step is traced when Langfuse is configured."""
import logging
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import cache, db
from .config import settings
from .guard import check_intent
from .llm import generate_sql
from .prompt import build_system_prompt
from .retrieval import build_context
from .tracing import observe, update_current_span
from .validate import ValidationError, validate_sql

logger = logging.getLogger(__name__)

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
    cache_hit: bool = False
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    error_stage: str | None = None
    query_cost: float | None = None
    attempts: list[Attempt] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


@observe(name="gates-and-execute", capture_output=False)
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
    # Only a summary is traced, never the rows themselves.
    update_current_span(output={"cost": cost, "row_count": len(rows), "truncated": truncated})
    return sql, cost, columns, rows, truncated


@observe(name="cache-lookup", capture_input=False)
async def _answer_from_cache(res: PipelineResult, question: str) -> bool:
    """Fill `res` from the cache if possible. Cached SQL is re-validated and re-run, never trusted blindly."""
    cached = await cache.get(question)
    if not cached:
        return False
    if cached.get("refused"):
        res.refused = True
        res.refusal_category = cached.get("refusal_category")
        res.refusal_reason = cached.get("refusal_reason")
        res.cache_hit = True
        return True
    try:
        res.sql, res.query_cost, res.columns, res.rows, res.truncated = await _gate_and_execute(cached["sql"])
    except StageError as exc:
        logger.warning("cached SQL no longer runs (%s); generating a fresh answer", exc)
        return False
    res.tables_used = cached.get("tables_used", [])
    res.schema_tables = cached.get("schema_tables", [])
    res.terms_used = cached.get("terms_used", [])
    res.confidence = cached.get("confidence", 0.0)
    res.attempts.append(Attempt(sql=res.sql))
    res.cache_hit = True
    return True


@observe(name="answer-question", capture_output=False)
async def answer(question: str, use_cache: bool = True) -> PipelineResult:
    res = await _answer(question, use_cache)
    # The root span's output becomes the trace output: a compact outcome, not the full result.
    update_current_span(output={
        "status": "refused" if res.refused else ("error" if res.error else "ok"),
        "sql": res.sql,
        "row_count": len(res.rows),
        "cache_hit": res.cache_hit,
        "attempts": len(res.attempts),
        "error_stage": res.error_stage,
        "refusal_category": res.refusal_category,
    })
    return res


async def _answer(question: str, use_cache: bool) -> PipelineResult:
    res = PipelineResult(question=question)

    # 1. Deterministic check: requests to change data are refused before any LLM call.
    blocked = check_intent(question)
    if blocked:
        res.refused = True
        res.refusal_category, res.refusal_reason = blocked
        return res

    # 2. Cache: a previously answered question skips the LLM entirely.
    if use_cache and await _answer_from_cache(res, question):
        return res

    # 3. Build the prompt context: relevant tables, business definitions, similar examples.
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

        # 4. The model judged the question unanswerable, or produced no usable query: refuse, never guess.
        if not generated.answerable or not generated.sql.strip():
            res.refused = True
            res.refusal_category = generated.refusal_category or "unclear"
            res.refusal_reason = generated.refusal_reason or "This question can't be answered from this database."
            res.sql, res.error, res.error_stage = "", None, None
            res.attempts.append(Attempt(sql="", error=res.refusal_reason, stage="refusal"))
            if use_cache:
                await cache.put(question, {
                    "refused": True, "refusal_category": res.refusal_category, "refusal_reason": res.refusal_reason,
                })
            break

        # 5. Safety gates and execution, with self-correction on failure.
        res.sql = generated.sql
        try:
            res.sql, res.query_cost, res.columns, res.rows, res.truncated = await _gate_and_execute(generated.sql)
            res.error = res.error_stage = None
            res.attempts.append(Attempt(sql=res.sql))
            if use_cache:  # only successful answers are cached; errors never are
                await cache.put(question, {
                    "sql": res.sql, "tables_used": res.tables_used, "schema_tables": res.schema_tables,
                    "terms_used": res.terms_used, "confidence": res.confidence,
                })
            break
        except StageError as exc:
            res.error, res.error_stage = str(exc), exc.stage
            res.attempts.append(Attempt(sql=generated.sql, error=res.error, stage=exc.stage))
            feedback.append((generated.sql, res.error))

    return res