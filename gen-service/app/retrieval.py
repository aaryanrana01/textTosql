"""Prompt context: relevant tables (pgvector + join paths), similar worked examples (pgvector)
and business definitions (semantic layer)."""
import asyncio
import logging
from pathlib import Path

from fastembed import TextEmbedding

from . import db
from .config import settings
from .prompt import PromptContext
from .schema_text import CATALOG
from .semantic import match_terms
from .tracing import observe, update_current_span

logger = logging.getLogger(__name__)

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384 dimensions, small and fast on CPU
EMBED_DIM = 384

# The model files are kept inside the service folder (gen-service/.model_cache), so a hosting build step
# can download them once. A sleeping server that wakes up then only loads the model from disk,
# instead of downloading 67 MB again on every start.
MODEL_CACHE_DIR = Path(__file__).resolve().parents[1] / ".model_cache"

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """Load the embedding model once (downloaded into MODEL_CACHE_DIR only if it isn't there yet)."""
    global _model
    if _model is None:
        _model = TextEmbedding(EMBED_MODEL, cache_dir=str(MODEL_CACHE_DIR))
    return _model


def to_vector_literal(vector) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vector) + "]"


def embed_query(text: str) -> str:
    return to_vector_literal(next(iter(get_model().query_embed([text]))))


@observe(name="retrieve-context", capture_output=False)
async def build_context(question: str) -> PromptContext:
    terms = match_terms(question)
    tables = set(CATALOG.table_names)
    examples: list[dict] = []

    if settings.schema_retrieval or settings.few_shot_k:
        # Embedding is CPU work; a thread keeps it from blocking other requests.
        vector = await asyncio.to_thread(embed_query, question)
        async with db.app_pool.connection() as conn:
            if settings.schema_retrieval:
                cur = await conn.execute(
                    "SELECT table_name FROM app.schema_index ORDER BY embedding <=> %s::vector LIMIT %s",
                    (vector, settings.retrieval_top_k),
                )
                retrieved = [row[0] for row in await cur.fetchall()]
                if retrieved:
                    term_tables = [t for term in terms for t in term.get("tables", [])]
                    tables = CATALOG.connect(retrieved + term_tables)
                else:
                    logger.warning("schema index is empty; falling back to the full schema")
            if settings.few_shot_k:
                cur = await conn.execute(
                    "SELECT question, sql FROM app.example_index ORDER BY embedding <=> %s::vector LIMIT %s",
                    (vector, settings.few_shot_k),
                )
                examples = [{"question": q, "sql": s} for q, s in await cur.fetchall()]

    # Only a compact summary goes to the trace, not the whole prompt context.
    update_current_span(output={
        "tables": sorted(tables), "terms": [t["name"] for t in terms], "examples": len(examples),
    })
    return PromptContext(schema_text=CATALOG.render(tables), tables=sorted(tables), terms=terms, examples=examples)