import asyncio

from app import pipeline
from app.llm import GeneratedSQL

import pytest


@pytest.fixture(autouse=True)
def fake_schema(monkeypatch):
    async def schema_for(question):
        return "film: The film catalog.\n  film_id integer PK", ["film"]

    monkeypatch.setattr(pipeline, "schema_for", schema_for)



GOOD = "SELECT count(*) FROM film"
BAD = "SELECT nope FROM film"


def fake_llm(sql_sequence):
    """Returns the given SQL strings in order, and records the feedback each call received."""
    calls = []

    async def generate(question, schema_text, feedback=None):
        calls.append(list(feedback or []))
        sql = sql_sequence[min(len(calls) - 1, len(sql_sequence) - 1)]
        return GeneratedSQL(sql=sql, tables_used=["film"], confidence=0.9), {"prompt_tokens": 10, "completion_tokens": 5}

    return generate, calls


async def fake_gate(sql):
    if "nope" in sql:
        raise pipeline.StageError("execution", 'column "nope" does not exist')
    return sql, 1.0, ["count"], [[1000]], False


def test_retry_fixes_a_failed_query(monkeypatch):
    generate, calls = fake_llm([BAD, GOOD])
    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "_gate_and_execute", fake_gate)

    res = asyncio.run(pipeline.answer("How many films?"))

    assert res.error is None and res.rows == [[1000]]
    assert len(res.attempts) == 2
    assert 'column "nope" does not exist' in calls[1][0][1]  # the 2nd call saw the 1st error
    assert res.usage == {"prompt_tokens": 20, "completion_tokens": 10}  # both calls counted


def test_gives_up_after_max_attempts(monkeypatch):
    generate, calls = fake_llm([BAD])
    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "_gate_and_execute", fake_gate)

    res = asyncio.run(pipeline.answer("How many films?"))

    assert res.error_stage == "execution"
    assert len(res.attempts) == len(calls) == pipeline.MAX_ATTEMPTS


def test_does_not_retry_when_model_declines(monkeypatch):
    generate, calls = fake_llm([""])
    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "_gate_and_execute", fake_gate)

    res = asyncio.run(pipeline.answer("Drop the customer table."))

    assert res.error == "the model returned no SQL"
    assert len(calls) == 1