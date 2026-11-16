"""Postgres connection helper (pgvector registered)."""

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from finsight.config import get_settings
from finsight.models import Chunk


def connect() -> psycopg.Connection:
    """Open a connection with the pgvector type registered."""
    conn = psycopg.connect(get_settings().database_url)
    register_vector(conn)
    return conn


def replace_report(
    company: str, fiscal_year: str, chunks: list[Chunk], embeddings: np.ndarray
) -> None:
    """Atomically replace all rows of one report (idempotent re-ingestion)."""
    rows = [
        (c.company, c.fiscal_year, c.page, c.section, c.content, c.is_table, e)
        for c, e in zip(chunks, embeddings, strict=True)
    ]
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "delete from chunks where company = %s and fiscal_year = %s", (company, fiscal_year)
        )
        cur.executemany(
            "insert into chunks (company, fiscal_year, page, section, content, is_table, embedding)"
            " values (%s, %s, %s, %s, %s, %s, %s)",
            rows,
        )


def ping() -> bool:
    """Return True if the database answers `select 1`."""
    with connect() as conn:
        return conn.execute("select 1").fetchone() == (1,)
