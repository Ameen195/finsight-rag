"""Reciprocal Rank Fusion of several ranked lists."""

from finsight.models import RetrievedChunk

RRF_K = 60


def rrf(
    ranked_lists: list[list[RetrievedChunk]],
    k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Fuse ranked lists: score(chunk) = sum over lists of weight / (k + rank), rank from 1.

    `weights` defaults to 1.0 per list (plain RRF). A chunk found by several retrievers keeps
    every retriever's own score; ties keep the order of first appearance.
    """
    weights = weights or [1.0] * len(ranked_lists)
    fused: dict[int, RetrievedChunk] = {}
    for ranked, weight in zip(ranked_lists, weights, strict=True):
        for rank, item in enumerate(ranked, start=1):
            key = item.chunk.id
            current = fused.setdefault(key, item.model_copy(update={"rrf_score": 0.0}))
            updates = {f: v for f, v in item.model_dump(exclude={"chunk"}).items() if v is not None}
            updates["rrf_score"] = current.rrf_score + weight / (k + rank)
            fused[key] = current.model_copy(update=updates)
    return sorted(fused.values(), key=lambda r: r.rrf_score, reverse=True)
