"""Postgres connection helper (pgvector registered)."""

import psycopg
from pgvector.psycopg import register_vector

from finsight.config import get_settings


def connect() -> psycopg.Connection:
    """Open a connection with the pgvector type registered."""
    conn = psycopg.connect(get_settings().database_url)
    register_vector(conn)
    return conn


def ping() -> bool:
    """Return True if the database answers `select 1`."""
    with connect() as conn:
        return conn.execute("select 1").fetchone() == (1,)
