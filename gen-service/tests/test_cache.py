import asyncio

import pytest

from app import cache, pipeline
from app.llm import GeneratedSQL
from app.prompt import PromptContext


def test_normalize_ignores_case_spacing_and_trailing_punctuation():
    assert cache.normalize("  How many   FILMS are there? ") == cache.normalize("how many films are there")


def test_key_changes_when_the_fingerprint_changes(monkeypatch):
    before = cache._key("How many films?")
    monkeypatch.setattr(cache, "VERSION", "something-changed")
    assert cache._key("How many films?") != before


@pytest.fixture
def fakes(monkeypatch):
    """Fake retrieval and gates; records LLM calls and cache writes."""
    calls, stored = [], {}

    async def build_context(question):
        return PromptContext(schema_text="film: x", tables=["film"])

    async def generate(question, system_prompt, feedback=None):
        calls.append(question)
        return GeneratedSQL(sql="SELECT count(*) FROM film", tables_used=["film"], confidence=0.9), \
            {"prompt_tokens": 10, "completion_tokens": 5}

    async def gate(sql):
        return sql, 1.0, ["count"], [[1000]], False

    async def put(question, entry):
        stored[question] = entry

    monkeypatch.setattr(pipeline, "build_context", build_context)
    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "_gate_and_execute", gate)
    monkeypatch.setattr(pipeline.cache, "put", put)
    return calls, stored


def test_cache_hit_skips_the_llm_and_reruns_the_sql(monkeypatch, fakes):
    calls, _ = fakes

    async def get(question):
        return {"sql": "SELECT count(*) FROM film", "tables_used": ["film"], "schema_tables": ["film"],
                "terms_used": [], "confidence": 0.9}

    monkeypatch.setattr(pipeline.cache, "get", get)
    res = asyncio.run(pipeline.answer("How many films?"))
    assert res.cache_hit and res.rows == [[1000]]
    assert calls == []  # the LLM was never called
    assert res.usage == {"prompt_tokens": 0, "completion_tokens": 0}


def test_cached_refusal_is_returned_without_the_llm(monkeypatch, fakes):
    calls, _ = fakes

    async def get(question):
        return {"refused": True, "refusal_category": "not_in_data", "refusal_reason": "No weather data."}

    monkeypatch.setattr(pipeline.cache, "get", get)
    res = asyncio.run(pipeline.answer("What's the weather?"))
    assert res.cache_hit and res.refused and res.refusal_category == "not_in_data"
    assert calls == []


def test_successful_answers_are_cached(monkeypatch, fakes):
    calls, stored = fakes

    async def get(question):
        return None

    monkeypatch.setattr(pipeline.cache, "get", get)
    res = asyncio.run(pipeline.answer("How many films?"))
    assert not res.cache_hit and len(calls) == 1
    assert stored["How many films?"]["sql"] == "SELECT count(*) FROM film"


def test_cache_is_bypassed_when_disabled(monkeypatch, fakes):
    calls, stored = fakes
    reads = []

    async def get(question):
        reads.append(question)
        return {"sql": "SELECT 1"}

    monkeypatch.setattr(pipeline.cache, "get", get)
    res = asyncio.run(pipeline.answer("How many films?", use_cache=False))
    assert reads == [] and stored == {}  # neither read nor written
    assert not res.cache_hit and len(calls) == 1