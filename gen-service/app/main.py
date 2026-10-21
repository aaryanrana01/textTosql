import time
from contextlib import asynccontextmanager
from typing import Any

import openai
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import ROOT
from .llm import generate_sql
from .schema_text import load_schema_text

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
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False
    error: str | None = None
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

    # 2. Run the SQL as the read-only reader role
    columns, rows, truncated, error = [], [], False, None
    try:
        columns, rows, truncated = await db.run_query(result.sql)
    except psycopg.Error as exc:
        error = str(exc).strip()

    # 3. Return everything, including timing and token usage
    return GenerateResponse(
        question=req.question,
        sql=result.sql,
        tables_used=result.tables_used,
        confidence=result.confidence,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        error=error,
        latency_ms=int((time.perf_counter() - start) * 1000),
        usage=usage,
    )