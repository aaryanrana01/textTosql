"""Answer cache: stores the generated SQL (not the rows) for each normalised question.
A hit skips the LLM entirely; the SQL is still validated and re-run, so results are never stale."""
import hashlib
import json
import logging
import re

from redis.asyncio import Redis

from .config import ROOT, settings
from .prompt import RULES

logger = logging.getLogger(__name__)

# Created lazily: no connection is opened until the first command.
_client: Redis | None = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None


def _fingerprint() -> str:
    """Changes whenever anything that shapes an answer changes, so old entries are never reused."""
    h = hashlib.sha256()
    for name in ("db/schema.json", "db/schema_docs.yaml", "db/semantic_layer.yaml", "db/examples.jsonl"):
        h.update((ROOT / name).read_bytes())
    h.update(RULES.encode())
    h.update(settings.llm_model.encode())
    h.update(repr((settings.schema_retrieval, settings.retrieval_top_k, settings.few_shot_k,
                   settings.llm_reasoning_effort)).encode())
    return h.hexdigest()[:16]


VERSION = _fingerprint()


def normalize(question: str) -> str:
    """'  How many FILMS?' and 'how many films' are the same question."""
    return re.sub(r"\s+", " ", question.strip().lower()).rstrip(" ?.!")


def _key(question: str) -> str:
    return f"tts:{VERSION}:{hashlib.sha256(normalize(question).encode()).hexdigest()}"


async def get(question: str) -> dict | None:
    if _client is None:
        return None
    try:
        raw = await _client.get(_key(question))
        return json.loads(raw) if raw else None
    except Exception as exc:  # a cache outage must never break a request
        logger.warning("cache read failed: %s", exc)
        return None


async def put(question: str, entry: dict) -> None:
    if _client is None:
        return
    try:
        await _client.set(_key(question), json.dumps(entry), ex=settings.cache_ttl_seconds)
    except Exception as exc:
        logger.warning("cache write failed: %s", exc)


async def close() -> None:
    if _client is not None:
        await _client.aclose()