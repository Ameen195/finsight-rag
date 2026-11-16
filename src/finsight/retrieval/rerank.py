"""Cross-encoder reranking (default BAAI/bge-reranker-base)."""

from functools import lru_cache

import torch
from sentence_transformers import CrossEncoder

from finsight.config import get_settings
from finsight.models import RetrievedChunk


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """Load the reranker once, on first use (optionally int8-quantised for CPU speed)."""
    s = get_settings()
    model = CrossEncoder(s.reranker_model, max_length=s.reranker_max_length)
    if s.reranker_quantize:
        torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True
        )
    return model


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
