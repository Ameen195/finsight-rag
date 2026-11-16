"""Keyword retrieval: Postgres full-text search with an OR fallback.

`websearch_to_tsquery` ANDs every term, so a long natural question often matches nothing.
If the strict query returns fewer than k chunks, the same terms are OR-ed and the extra
results are appended after the strict ones. Figures such as 1,78,650 become phrase queries
('1' <-> '78' <-> '650') and stay exact in both modes.
"""

import re
from functools import lru_cache

from finsight.config import get_settings
from finsight.db import shared_connection
from finsight.models import RetrievedChunk
from finsight.retrieval.filters import COMPANY_ALIASES, Filters, extract_companies
from finsight.retrieval.sql import CHUNK_COLUMNS, to_retrieved, where_clause

# words that match almost every chunk of an annual report once OR-ed
GENERIC_WORDS = "per share price much fiscal global"
_YEAR_LEXEME = re.compile(r"^(?:fy\d{2,4}|(?:19|20)\d{2})$")


def prune_or_terms(loose: str, drop: frozenset[str]) -> str | None:
    """Remove single-lexeme OR operands in `drop` or that are years (2026, fy2026).

    Phrases ('1' <-> '78' <-> '650') and grouped operands are kept. None if nothing is left.
    """
    kept = [
        t
        for t in loose.split(" | ")
        if not (re.fullmatch(r"'[^']*'", t) and (t[1:-1] in drop or _YEAR_LEXEME.match(t[1:-1])))
    ]
    return " | ".join(kept) or None


@lru_cache(maxsize=128)
def _lexemes(text: str) -> frozenset[str]:
    """Postgres 'english' lexemes of `text` (same stemming as the fts column)."""
    rows = (
        shared_connection()
        .execute("select unnest(tsvector_to_array(to_tsvector('english', %s)))", (text,))
        .fetchall()
    )
    return frozenset(r[0] for r in rows)


def _drop_lexemes(query: str, filters: Filters) -> frozenset[str]:
    companies = set(filters.companies) | set(extract_companies(query))
    aliases = " ".join(a for c in sorted(companies) for a in COMPANY_ALIASES.get(c, []))
    return _lexemes(f"{aliases} {GENERIC_WORDS}")


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
    if loose and get_settings().keyword_fallback_prune:
        loose = prune_or_terms(loose, _drop_lexemes(query, filters))
    if loose:
        seen = {r.chunk.id for r in results}
        for r in _rank("%s::tsquery", loose, k, filters):
            if r[1] is not None and r[1] not in seen and len(results) < k:
                results.append(to_retrieved(r[1:], keyword_score=r[8]))
    return results
