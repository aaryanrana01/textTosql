import asyncio
import hmac
import time
from contextlib import asynccontextmanager
from typing import Any

import openai
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import cache, db, pipeline, retrieval, tracing
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.pool.open()
    await db.app_pool.open()
    await asyncio.to_thread(retrieval.get_model)  # load the embedding model before the first request
    yield
    tracing.shutdown()
    await cache.close()
    await db.app_pool.close()
    await db.pool.close()


app = FastAPI(title="Text-to-SQL generation service", lifespan=lifespan)


class GenerateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    use_cache: bool = True  # evaluations turn this off so they always measure the model, not the cache


class AttemptOut(BaseModel):
    sql: str
    error: str | None = None
    stage: str | None = None


class GenerateResponse(BaseModel):
    question: str
    sql: str
    tables_used: list[str]
    schema_tables: list[str] = []
    terms_used: list[str] = []
    examples_used: list[str] = []
    confidence: float
    refused: bool = False
    refusal_category: str | None = None
    refusal_reason: str | None = None
    cache_hit: bool = False
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
    error_stage: str | None = None
    query_cost: float | None = None
    attempts: int = 1
    attempt_history: list[AttemptOut] = []
    latency_ms: int
    usage: dict


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _log_llm_failure(question: str, start: float, error: str) -> None:
    await db.log_request({
        "question": question, "status": "llm_error", "error_stage": "llm", "error": error,
        "attempts": 0, "attempt_errors": [], "latency_ms": _elapsed_ms(start), "model": settings.llm_model,
    })


async def verify_internal_token(x_internal_token: str | None = Header(default=None)):
    """When a token is configured, only callers that send it (the Express API) may use /generate."""
    if settings.internal_api_token and not hmac.compare_digest(
        x_internal_token or "", settings.internal_api_token
    ):
        raise HTTPException(status_code=401, detail="invalid internal token")


@app.get("/health")
async def health():
    _, rows, _ = await db.run_query("SELECT 1")
    return {"status": "ok", "database": rows[0][0] == 1}


@app.post("/generate", response_model=GenerateResponse, dependencies=[Depends(verify_internal_token)])
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    start = time.perf_counter()
    if settings.daily_token_budget:
        used = await db.tokens_used_today()
        if used >= settings.daily_token_budget:
            raise HTTPException(
                status_code=429,
                detail="The daily demo limit has been reached. Please try again tomorrow.",
            )

    try:
        res = await pipeline.answer(req.question, use_cache=req.use_cache)
    except openai.RateLimitError as exc:
        await _log_llm_failure(req.question, start, f"rate limit: {exc.message}")
        raise HTTPException(status_code=429, detail=f"LLM rate limit: {exc.message}")
    except openai.APITimeoutError:
        await _log_llm_failure(req.question, start, "timeout")
        raise HTTPException(status_code=504, detail="LLM timed out")
    except Exception as exc:
        await _log_llm_failure(req.question, start, str(exc)[:500])
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    latency_ms = _elapsed_ms(start)
    attempt_errors = [{"sql": a.sql, "stage": a.stage, "error": a.error} for a in res.attempts if a.error]

    if res.refused:
        status, stage, error = "refused", "refusal", f"{res.refusal_category}: {res.refusal_reason}"
    else:
        status = "ok" if res.error is None else "error"
        stage, error = res.error_stage, res.error

    # Logged after the response is sent, so logging never adds latency for the user.
    background_tasks.add_task(db.log_request, {
        "question": req.question,
        "final_sql": res.sql or None,
        "status": status,
        "error_stage": stage,
        "error": error,
        "attempts": len(res.attempts),
        "attempt_errors": attempt_errors,
        "row_count": len(res.rows),
        "truncated": res.truncated,
        "query_cost": res.query_cost,
        "latency_ms": latency_ms,
        "prompt_tokens": res.usage["prompt_tokens"],
        "completion_tokens": res.usage["completion_tokens"],
        "model": settings.llm_model,
        "cache_hit": res.cache_hit,
    })

    return GenerateResponse(
        question=req.question,
        sql=res.sql,
        tables_used=res.tables_used,
        schema_tables=res.schema_tables,
        terms_used=res.terms_used,
        examples_used=res.examples_used,
        confidence=res.confidence,
        refused=res.refused,
        refusal_category=res.refusal_category,
        refusal_reason=res.refusal_reason,
        cache_hit=res.cache_hit,
        columns=res.columns,
        rows=res.rows,
        row_count=len(res.rows),
        truncated=res.truncated,
        error=res.error,
        error_stage=res.error_stage,
        query_cost=res.query_cost,
        attempts=len(res.attempts),
        attempt_history=[AttemptOut(**vars(a)) for a in res.attempts],
        latency_ms=latency_ms,
        usage=res.usage,
    )