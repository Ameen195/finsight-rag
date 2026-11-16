import time

from finsight.config import Settings
from finsight.generation.llm import TPMLimiter


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert (s.retrieval_top_k, s.rerank_top_n, s.max_context_tokens) == (20, 5, 3000)
    assert s.langfuse_public_key is None


def test_tpm_limiter_blocks_when_budget_full() -> None:
    lim = TPMLimiter(limit=100, window=0.3)
    lim.acquire(80)
    start = time.monotonic()
    lim.acquire(50)  # does not fit until the first event leaves the window
    assert time.monotonic() - start >= 0.25
