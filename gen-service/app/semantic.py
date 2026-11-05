"""Semantic layer: match business terms in a question to the company's definitions."""
import re

import yaml

from .config import ROOT

TERMS: list[dict] = yaml.safe_load((ROOT / "db" / "semantic_layer.yaml").read_text())["terms"]


def _phrase_pattern(phrase: str) -> re.Pattern:
    # Whole words only, any spacing between words, optional plural "s" at the end.
    words = phrase.lower().split()
    return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"s?\b")


_PATTERNS = [(term, [_phrase_pattern(p) for p in [term["name"], *term.get("synonyms", [])]]) for term in TERMS]


def match_terms(question: str) -> list[dict]:
    q = question.lower()
    return [term for term, patterns in _PATTERNS if any(p.search(q) for p in patterns)]
