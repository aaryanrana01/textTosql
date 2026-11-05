import json

import pytest

from app.config import ROOT
from app.guard import check_intent


@pytest.mark.parametrize("question", [
    "Delete all rentals.",
    "Please drop the customer table",
    "Update the rental rate of every film to 0.99.",
    "TRUNCATE payment",
    "Could you remove all inactive customers?",
    "insert a new film called TEST",
])
def test_flags_requests_to_change_data(question):
    assert check_intent(question)[0] == "modifies_data"


@pytest.mark.parametrize("question", [
    "How many rentals were updated last month?",
    "Which customers dropped off in 2025?",
    "What was the change in revenue between 2024 and 2025?",
])
def test_mentions_of_write_words_are_not_requests(question):
    assert check_intent(question) is None


def test_never_flags_answerable_benchmark_questions():
    items = [json.loads(l) for l in (ROOT / "evals" / "dataset.jsonl").read_text().splitlines() if l.strip()]
    flagged = [i["id"] for i in items if i["expect"] == "answer" and check_intent(i["question"])]
    assert not flagged, f"guard would wrongly refuse: {flagged}"