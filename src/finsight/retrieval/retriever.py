"""Single entry point for retrieval: `retrieve(query, mode, filters, k)`."""

from functools import lru_cache
from typing import Literal

from finsight.config import get_settings
from finsight.db import shared_connection
from finsight.ingest.embed import embed_query
from finsight.models import RetrievedChunk
from finsight.retrieval import dense, keyword
from finsight.retrieval.filters import Filters, extract_filters
from finsight.retrieval.hybrid import rrf
from finsight.retrieval.rerank import rerank

Mode = Literal["dense", "keyword", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("dense", "keyword", "hybrid", "hybrid_rerank")


@lru_cache(maxsize=1)
def stored_fiscal_years() -> frozenset[str]:
    """Fiscal years present in the DB (cached for the process)."""
    rows = shared_connection().execute("select distinct fiscal_year from chunks").fetchall()
    return frozenset(r[0] for r in rows)


def resolve_filters(query: str) -> Filters:
    """Filters from the question; a fiscal year not in the DB is dropped, not enforced.

    A question about FY2025 should still search the FY2026 report, whose tables carry
    prior-year figures.
    """
    f = extract_filters(query)
    return Filters(
        companies=f.companies,
        fiscal_years=[y for y in f.fiscal_years if y in stored_fiscal_years()],
    )


def retrieve(
    query: str, mode: Mode = "hybrid_rerank", filters: Filters | None = None, k: int | None = None
) -> list[RetrievedChunk]:
    """Retrieve the top-k chunks for `query` with the given mode."""
    s = get_settings()
    k = k or s.rerank_top_n
    filters = filters if filters is not None else resolve_filters(query)
    if mode == "dense":
        return dense.search(embed_query(query), k, filters)
    if mode == "keyword":
        return keyword.search(query, k, filters)
    pool = s.retrieval_top_k
    fused = rrf(
        [dense.search(embed_query(query), pool, filters), keyword.search(query, pool, filters)],
        weights=[1.0, s.rrf_keyword_weight],
    )
    fused = fused[:pool]
    if mode == "hybrid":
        return fused[:k]
    return rerank(query, fused)[:k]
