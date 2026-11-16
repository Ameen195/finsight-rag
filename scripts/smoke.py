"""Smoke check: DB ping, pgvector enabled, Groq call. Run: uv run python scripts/smoke.py"""

import sys
from collections.abc import Callable

from finsight.config import get_settings
from finsight.db import connect, ping
from finsight.generation.llm import complete


def check(name: str, fn: Callable[[], object]) -> bool:
    """Run one check and print PASS/FAIL (never prints secrets)."""
    try:
        print(f"PASS  {name}: {fn()}")
        return True
    except Exception as e:  # smoke script: report any failure
        print(f"FAIL  {name}: {type(e).__name__}: {e}")
        return False


def pgvector_enabled() -> str:
    """Confirm the vector extension and the chunks table exist."""
    with connect() as conn:
        row = conn.execute("select extversion from pg_extension where extname='vector'").fetchone()
        assert row, "extension 'vector' not installed"
        n = conn.execute("select count(*) from chunks").fetchone()[0]
        return f"vector {row[0]}, chunks table ok ({n} rows)"


def groq_hello() -> str:
    """Make one tiny completion with the small model."""
    messages = [{"role": "user", "content": "Say hello in 3 words."}]
    reply = complete(messages, get_settings().small_model, max_tokens=200).strip()
    assert reply, "empty reply (reasoning ate the token budget?)"
    return reply


if __name__ == "__main__":
    results = [
        check("db ping", ping),
        check("pgvector", pgvector_enabled),
        check("groq", groq_hello),
    ]
    sys.exit(0 if all(results) else 1)
