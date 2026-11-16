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
    reranker_model: str = "BAAI/bge-reranker-base"

    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    # weight of the keyword list in RRF (dense = 1.0); 0.5 beat 1.0 on Hit@1/MRR in the Phase 3 eval
    rrf_keyword_weight: float = 0.5
    max_context_tokens: int = 3000


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
