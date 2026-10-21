from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import settings

client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=60,
    max_retries=0,
)

RULES = """You are an expert PostgreSQL analyst.
Write ONE read-only PostgreSQL SELECT query that answers the user's question.

Rules:
- Use only the tables and columns listed in the schema below.
- Use the simplest query that answers the question. Do not join tables that are not needed.
- Join tables using the foreign keys shown with ->.
- Use only the allowed values shown in parentheses for enum columns.
- Respond with JSON only, in exactly this shape:
  {"sql": "<the query>", "tables_used": ["<table>", ...], "confidence": <number from 0 to 1>}

Schema:
"""


class GeneratedSQL(BaseModel):
    sql: str
    tables_used: list[str]
    confidence: float = Field(ge=0, le=1)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def generate_sql(question: str, schema_text: str) -> tuple[GeneratedSQL, dict]:
    extra = {}
    if settings.llm_reasoning_effort:
        extra["reasoning_effort"] = settings.llm_reasoning_effort

    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": RULES + schema_text},
            {"role": "user", "content": question},
        ],
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