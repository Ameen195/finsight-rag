"""Application settings, loaded from environment variables / `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration. Secrets come only from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    database_url: str = ""

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    big_model: str = "openai/gpt-oss-120b"
    small_model: str = "openai/gpt-oss-20b"
    groq_tpm_limit: int = 7000  # under Groq's 8,000 tokens/min free cap

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # 5.5x faster than BAAI/bge-reranker-base on CPU with equal Hit@1 in the Phase 3 eval
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    rerank_candidates: int | None = None  # rerank only the fused top-N (None = whole pool)
    reranker_max_length: int = 512
    reranker_quantize: bool = False  # dynamic int8 quantisation of the reranker's Linear layers
    # weight of the keyword list in RRF (dense = 1.0); 0.5 beat 1.0 on Hit@1/MRR in the Phase 3 eval
    rrf_keyword_weight: float = 0.5
    # drop company names, years and generic words from the keyword OR fallback
    # (doubled keyword Hit@5 in the Phase 3 eval at no latency cost)
    keyword_fallback_prune: bool = True
    max_context_tokens: int = 3000
    # refuse without calling the big model if the best rerank score is below this (None = off).
    # MiniLM gives raw logits that did not separate (un)answerable questions in the Phase 4 run
    # (Mars 0.13 vs an answerable comparison -1.35); tune with scores printed by scripts/ask.py
    min_rerank_score: float | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
