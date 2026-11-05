import asyncio

import pytest

from app import pipeline
from app.llm import GeneratedSQL
from app.prompt import PromptContext

GOOD = "SELECT count(*) FROM film"
BAD = "SELECT nope FROM film"
USAGE = {"prompt_tokens": 10, "completion_tokens": 5}


@pytest.fixture(autouse=True)
def fake_context(monkeypatch):
    """Replace retrieval so these tests need no database, embedding model or LLM."""
    async def build_context(question):
        return PromptContext(schema_text="film: The film catalog.\n  film_id integer PK", tables=["film"])

    monkeypatch.setattr(pipeline, "build_context", build_context)


def fake_llm(outputs):
    """Returns the given outputs in order (SQL strings or GeneratedSQL objects), recording each call's feedback."""
    calls = []

    async def generate(question, system_prompt, feedback=None):
        calls.append(list(feedback or []))
        out = outputs[min(len(calls) - 1, len(outputs) - 1)]
        if isinstance(out, str):
            out = GeneratedSQL(sql=out, tables_used=["film"], confidence=0.9)
        return out, dict(USAGE)

    return generate, calls


async def fake_gate(sql):
    if "nope" in sql:
        raise pipeline.StageError("execution", 'column "nope" does not exist')
    return sql, 1.0, ["count"], [[1000]], False


def run(monkeypatch, outputs, question="How many films?"):
    generate, calls = fake_llm(outputs)
    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "_gate_and_execute", fake_gate)
    return asyncio.run(pipeline.answer(question)), calls


def test_retry_fixes_a_failed_query(monkeypatch):
    res, calls = run(monkeypatch, [BAD, GOOD])
    assert res.error is None and res.rows == [[1000]] and not res.refused
    assert len(res.attempts) == 2
    assert 'column "nope" does not exist' in calls[1][0][1]  # the 2nd call saw the 1st error
    assert res.usage == {"prompt_tokens": 20, "completion_tokens": 10}  # both calls counted


def test_gives_up_after_max_attempts(monkeypatch):
    res, calls = run(monkeypatch, [BAD])
    assert res.error_stage == "execution" and not res.refused
    assert len(res.attempts) == len(calls) == pipeline.MAX_ATTEMPTS


def test_model_refusal_is_returned_and_not_retried(monkeypatch):
    refusal = GeneratedSQL(
        answerable=False, refusal_category="not_in_data",
        refusal_reason="The database has no weather data.", confidence=0.95,
    )
    res, calls = run(monkeypatch, [refusal], "What's the weather in Delhi?")
    assert res.refused and res.refusal_category == "not_in_data"
    assert res.refusal_reason == "The database has no weather data."
    assert len(calls) == 1 and res.rows == [] and res.sql == ""


def test_empty_sql_counts_as_unclear_refusal(monkeypatch):
    res, calls = run(monkeypatch, [""])
    assert res.refused and res.refusal_category == "unclear"
    assert len(calls) == 1


def test_write_requests_are_refused_without_calling_the_llm(monkeypatch):
    res, calls = run(monkeypatch, [GOOD], "Delete all rentals.")
    assert res.refused and res.refusal_category == "modifies_data"
    assert calls == []  # the LLM was never called
    assert res.usage == {"prompt_tokens": 0, "completion_tokens": 0}  # zero tokens spent