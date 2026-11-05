import json

import pytest

from app.config import ROOT
from app.prompt import PromptContext, build_system_prompt
from app.schema_text import CATALOG
from app.semantic import TERMS, match_terms
from app.validate import validate_sql


def matched(question):
    return {t["name"] for t in match_terms(question)}


@pytest.mark.parametrize("question,term", [
    ("How many VIP customers do we have?", "VIP customer"),
    ("What is our AOV?", "average order value"),
    ("How many churned customers are there?", "churned customer"),
    ("List our dormant titles.", "dormant title"),
    ("What was year-over-year revenue growth?", "year-over-year growth"),
    ("Which category is best performing?", "best performer"),
])
def test_matches_terms_synonyms_and_plurals(question, term):
    assert term in matched(question)


def test_no_false_matches_on_ordinary_words():
    # "average" alone must not trigger "average order value"; "active" alone must not trigger "active customer".
    assert matched("What is the average rental rate of films?") == set()
    assert matched("How many films are in each category?") == set()


def test_every_term_is_complete_and_uses_real_tables():
    for term in TERMS:
        assert term.get("definition") and term.get("sql"), f"incomplete term: {term['name']}"
        for table in term.get("tables", []):
            assert table in CATALOG.schema, f"{term['name']} uses unknown table {table}"


def test_definitions_reach_the_prompt():
    ctx = PromptContext(schema_text="film: x", terms=match_terms("How many VIP customers do we have?"))
    assert "greater than 250" in build_system_prompt(ctx)


EXAMPLES = [json.loads(l) for l in (ROOT / "db" / "examples.jsonl").read_text().splitlines() if l.strip()]
EVAL_QUESTIONS = {
    json.loads(l)["question"].lower()
    for l in (ROOT / "evals" / "dataset.jsonl").read_text().splitlines() if l.strip()
}


def test_examples_never_copy_eval_questions():
    leaked = [e["id"] for e in EXAMPLES if e["question"].lower() in EVAL_QUESTIONS]
    assert not leaked, f"examples duplicate evaluation questions: {leaked}"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e["id"])
def test_examples_pass_validation(example):
    validate_sql(example["sql"])
