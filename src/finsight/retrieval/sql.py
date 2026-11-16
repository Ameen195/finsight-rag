"""Shared SQL pieces for the search modules."""

from finsight.models import Chunk, RetrievedChunk
from finsight.retrieval.filters import Filters

CHUNK_COLUMNS = "c.id, c.company, c.fiscal_year, c.page, c.section, c.content, c.is_table"


def where_clause(filters: Filters) -> tuple[str, list]:
    """SQL `and ...` conditions + params for the metadata filters (empty list = no filter)."""
    sql, params = "", []
    if filters.companies:
        sql += " and c.company = any(%s)"
        params.append(filters.companies)
    if filters.fiscal_years:
        sql += " and c.fiscal_year = any(%s)"
        params.append(filters.fiscal_years)
    return sql, params


def to_retrieved(row: tuple, **scores: float) -> RetrievedChunk:
    """A row starting with CHUNK_COLUMNS -> RetrievedChunk with the given score fields."""
    id_, company, fy, page, section, content, is_table = row[:7]
    chunk = Chunk(
        id=id_,
        company=company,
        fiscal_year=fy,
        page=page,
        section=section,
        content=content,
        is_table=is_table,
    )
    return RetrievedChunk(chunk=chunk, **scores)
