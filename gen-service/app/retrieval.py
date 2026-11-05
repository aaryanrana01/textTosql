"""Schema retrieval: find the tables relevant to a question with pgvector, then add the tables needed to join them."""
import asyncio
import logging

from fastembed import TextEmbedding

from . import db
from .config import settings
from .schema_text import CATALOG

logger = logging.getLogger(__name__)

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384 dimensions, small and fast on CPU
EMBED_DIM = 384
_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """Load the embedding model once (it is downloaded on first use)."""
    global _model
    if _model is None:
        _model = TextEmbedding(EMBED_MODEL)
    return _model


def to_vector_literal(vector) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vector) + "]"


def embed_query(text: str) -> str:
    return to_vector_literal(next(iter(get_model().query_embed([text]))))


async def retrieve_tables(question: str) -> list[str]:
    # Embedding is CPU work; a thread keeps it from blocking other requests.
    vector = await asyncio.to_thread(embed_query, question)
    async with db.app_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT table_name FROM app.schema_index ORDER BY embedding <=> %s::vector LIMIT %s",
            (vector, settings.retrieval_top_k),
        )
        return [row[0] for row in await cur.fetchall()]


async def schema_for(question: str) -> tuple[str, list[str]]:
    """The schema text for this question's prompt, and the tables it contains."""
    tables = set(CATALOG.table_names)
    if settings.schema_retrieval:
        retrieved = await retrieve_tables(question)
        if retrieved:
            tables = CATALOG.connect(retrieved)
        else:
            logger.warning("schema index is empty; falling back to the full schema")
    return CATALOG.render(tables), sorted(tables)