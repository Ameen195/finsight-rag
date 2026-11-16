"""Keyword retrieval: Postgres full-text search with an OR fallback.

`websearch_to_tsquery` ANDs every term, so a long natural question often matches nothing.
If the strict query returns fewer than k chunks, the same terms are OR-ed and the extra
results are appended after the strict ones. Figures such as 1,78,650 become phrase queries
('1' <-> '78' <-> '650') and stay exact in both modes.
"""

from finsight.db import shared_connection
from finsight.models import RetrievedChunk
from finsight.retrieval.filters import Filters
from finsight.retrieval.sql import CHUNK_COLUMNS, to_retrieved, where_clause


def or_query(tsquery_text: str) -> str | None:
    """Turn a websearch tsquery's top-level ANDs into ORs; None if it cannot be loosened.

    Phrase operators (<->) bind tighter than & and |, so figures stay exact phrases.
    Negated terms (!) would match almost everything once OR-ed, so those queries stay strict.
    """
    if not tsquery_text or "!" in tsquery_text or " & " not in tsquery_text:
        return None
    return tsquery_text.replace(" & ", " | ")


def _rank(tsquery_sql: str, param: str, k: int, filters: Filters) -> list[tuple]:
    where, params = where_clause(filters)
    return (
        shared_connection()
        .execute(
            f"with q as (select {tsquery_sql} as tsq) "
            f"select q.tsq::text, {CHUNK_COLUMNS}, ts_rank_cd(c.fts, q.tsq) as rank "
            f"from q left join lateral (select * from chunks c where c.fts @@ q.tsq{where}"
            f" order by ts_rank_cd(c.fts, q.tsq) desc limit %s) c on true"
            f" order by rank desc nulls last",
            [param, *params, k],
        )
        .fetchall()
    )


def search(query: str, k: int, filters: Filters) -> list[RetrievedChunk]:
    """Top-k chunks by `ts_rank_cd`; strict matches first, then OR-fallback matches."""
    rows = _rank("websearch_to_tsquery('english', %s)", query, k, filters)
    strict_text = rows[0][0] if rows else ""
    results = [to_retrieved(r[1:], keyword_score=r[8]) for r in rows if r[1] is not None]
    loose = or_query(strict_text) if len(results) < k else None
    if loose:
        seen = {r.chunk.id for r in results}
        for r in _rank("%s::tsquery", loose, k, filters):
            if r[1] is not None and r[1] not in seen and len(results) < k:
                results.append(to_retrieved(r[1:], keyword_score=r[8]))
    return results
