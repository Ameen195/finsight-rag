"""Cross-encoder reranking (BAAI/bge-reranker-base)."""

from functools import lru_cache

from sentence_transformers import CrossEncoder

from finsight.config import get_settings
from finsight.models import RetrievedChunk


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """Load the reranker once, on first use."""
    return CrossEncoder(get_settings().reranker_model, max_length=512)


def rerank(query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Score every (query, chunk) pair and return candidates sorted by `rerank_score`."""
    if not candidates:
        return []
    scores = get_reranker().predict([(query, c.chunk.content) for c in candidates])
    scored = [
        c.model_copy(update={"rerank_score": float(s)})
        for c, s in zip(candidates, scores, strict=True)
    ]
    return sorted(scored, key=lambda c: c.rerank_score, reverse=True)
