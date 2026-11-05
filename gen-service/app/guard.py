"""Deterministic intent check, run before the LLM: requests to change data are refused without spending tokens."""
import re

# Only a write verb at the START of the request counts, so questions that merely mention
# these words ("How many rentals were updated?", "Which customers dropped off?") are not affected.
WRITE_INTENT = re.compile(
    r"^\s*(?:please\s+|can you\s+|could you\s+)?"
    r"(?:delete|drop|truncate|update|insert|alter|remove|erase|wipe|modify|grant|revoke)\b",
    re.IGNORECASE,
)


def check_intent(question: str) -> tuple[str, str] | None:
    """Returns (category, reason) if the request must be refused, otherwise None."""
    if WRITE_INTENT.search(question):
        return "modifies_data", "You can ask any question about the data, but it will never change, delete or add records."
    return None