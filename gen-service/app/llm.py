import json

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import settings

client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=60,
    max_retries=0,
)


class GeneratedSQL(BaseModel):
    answerable: bool = True
    sql: str = ""
    tables_used: list[str] = []
    confidence: float = Field(default=0.0, ge=0, le=1)
    refusal_category: str | None = None
    refusal_reason: str | None = None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def generate_sql(
    question: str,
    system_prompt: str,
    feedback: list[tuple[str, str]] | None = None,
) -> tuple[GeneratedSQL, dict]:
    """Generate SQL. `feedback` holds (previous_sql, error) pairs from failed attempts."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    for previous_sql, error in feedback or []:
        messages.append({"role": "assistant", "content": json.dumps({"sql": previous_sql})})
        messages.append({
            "role": "user",
            "content": (
                f"That query failed: {error}\n"
                "Write a corrected query that answers the original question. "
                "Respond with JSON only, in the same shape as before."
            ),
        })

    extra = {}
    if settings.llm_reasoning_effort:
        extra["reasoning_effort"] = settings.llm_reasoning_effort

    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0,
        max_completion_tokens=2048,
        response_format={"type": "json_object"},
        **extra,
    )

    content = _strip_fences(response.choices[0].message.content or "")
    result = GeneratedSQL.model_validate_json(content)

    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
    return result, usage
