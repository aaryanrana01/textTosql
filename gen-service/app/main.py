import time
from contextlib import asynccontextmanager
from typing import Any

import openai
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import ROOT, settings
from .llm import generate_sql
from .schema_text import load_schema_text
from .validate import ValidationError, validate_sql

SCHEMA_TEXT = load_schema_text(ROOT / "db" / "schema.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.pool.open()
    yield
    await db.pool.close()


app = FastAPI(title="Text-to-SQL generation service", lifespan=lifespan)


class GenerateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class GenerateResponse(BaseModel):
    question: str
    sql: str
    tables_used: list[str]
    confidence: float
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
    error_stage: str | None = None  # "validation", "cost" or "execution"
    query_cost: float | None = None
    latency_ms: int
    usage: dict


@app.get("/health")
async def health():
    _, rows, _ = await db.run_query("SELECT 1")
    return {"status": "ok", "database": rows[0][0] == 1}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    start = time.perf_counter()

    # 1. Ask the LLM for SQL
    try:
        result, usage = await generate_sql(req.question, SCHEMA_TEXT)
    except openai.RateLimitError as exc:
        raise HTTPException(status_code=429, detail=f"LLM rate limit: {exc.message}")
    except openai.APITimeoutError:
        raise HTTPException(status_code=504, detail="LLM timed out")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    # 2. Safety gates: validate the SQL, then check its estimated cost
    sql, error, stage, cost = result.sql, None, None, None
    try:
        sql = validate_sql(result.sql)
        cost = await db.explain_cost(sql)
        if cost > settings.max_query_cost:
            error = f"query too expensive (estimated cost {cost:,.0f} exceeds limit {settings.max_query_cost:,.0f})"
            stage = "cost"
    except ValidationError as exc:
        error, stage = f"rejected by validation: {exc}", "validation"
    except psycopg.Error as exc:
        error, stage = str(exc).strip(), "execution"  # e.g. a column that doesn't exist

    # 3. Run it as the read-only reader role, only if every gate passed
    columns, rows, truncated = [], [], False
    if error is None:
        try:
            columns, rows, truncated = await db.run_query(sql)
        except psycopg.Error as exc:
            error, stage = str(exc).strip(), "execution"

    return GenerateResponse(
        question=req.question,
        sql=sql,
        tables_used=result.tables_used,
        confidence=result.confidence,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        error=error,
        error_stage=stage,
        query_cost=cost,
        latency_ms=int((time.perf_counter() - start) * 1000),
        usage=usage,
    )