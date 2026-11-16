"""Shared Pydantic models."""

from pydantic import BaseModel


class Chunk(BaseModel):
    """A piece of an annual report, as stored in the `chunks` table."""

    id: int | None = None
    company: str
    fiscal_year: str
    page: int
    section: str | None = None
    content: str
    is_table: bool = False


class RetrievedChunk(BaseModel):
    """A chunk plus the score from each retrieval stage (None if that stage didn't run)."""

    chunk: Chunk
    dense_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class Citation(BaseModel):
    """A source reference rendered as `[Company, FY, p.X]`."""

    company: str
    fiscal_year: str
    page: int
    snippet: str = ""
    text: str = ""  # full chunk text, for a source panel


class AnswerResponse(BaseModel):
    """Final agent output."""

    answer: str
    citations: list[Citation] = []
    question_type: str = "single"
    refused: bool = False
    latency_ms: int = 0
    trace_id: str | None = None
