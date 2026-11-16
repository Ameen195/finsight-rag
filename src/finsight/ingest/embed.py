"""bge-small embedding wrapper (lazy singleton)."""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from finsight.config import get_settings

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load the embedding model once, on first use."""
    return SentenceTransformer(get_settings().embedding_model)


def embed_passages(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed passages (no prefix), L2-normalised."""
    return get_model().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 100
    )


def embed_query(query: str) -> np.ndarray:
    """Embed a search query with the bge v1.5 query prefix."""
    return get_model().encode(QUERY_PREFIX + query, normalize_embeddings=True)
