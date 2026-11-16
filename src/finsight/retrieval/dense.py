"""Dense retrieval: cosine similarity over bge-small embeddings (pgvector `<=>`)."""

import numpy as np

from finsight.db import shared_connection
from finsight.models import RetrievedChunk
from finsight.retrieval.filters import Filters
from finsight.retrieval.sql import CHUNK_COLUMNS, to_retrieved, where_clause


def search(query_vec: np.ndarray, k: int, filters: Filters) -> list[RetrievedChunk]:
    """Top-k chunks by cosine similarity; `dense_score` = 1 - cosine distance."""
    where, params = where_clause(filters)
    rows = (
        shared_connection()
        .execute(
            f"select {CHUNK_COLUMNS}, c.embedding <=> %s as distance from chunks c"
            f" where true{where} order by c.embedding <=> %s limit %s",  # expression → HNSW index
            [query_vec, *params, query_vec, k],
        )
        .fetchall()
    )
    return [to_retrieved(r, dense_score=1 - r[7]) for r in rows]
