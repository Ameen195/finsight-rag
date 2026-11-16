"""FastAPI backend: cited answers (plain and NDJSON-streamed), companies, health, rate limit."""

import json
import logging
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import groq
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints, field_validator

from finsight import db
from finsight.config import get_settings
from finsight.generation import agent
from finsight.ingest import embed
from finsight.models import AnswerResponse
from finsight.retrieval import rerank
from finsight.retrieval.filters import COMPANY_ALIASES

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
WINDOW_SECONDS = 3600
UNAVAILABLE = "The service is temporarily unavailable. Please try again shortly."

AnswerFn = Callable[[str, list[str] | None], tuple[AnswerResponse, dict]]
StreamFn = Callable[[str, list[str] | None], Iterator[dict]]


def _warm_up() -> None:
    """Load the models and open the DB connection so the first request is fast."""
    for name, load in (
        ("embedder", embed.get_model),
        ("reranker", rerank.get_reranker),
        ("database", db.shared_connection),
    ):
        try:
            load()
        except Exception:  # noqa: BLE001 - warm-up must never stop the server from starting
            log.exception("warm-up of %s failed; continuing", name)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN201
    """Warm up on startup (skipped when tests use TestClient without a `with` block)."""
    _warm_up()
    yield


app = FastAPI(title="FinSight RAG", lifespan=lifespan)


class AskRequest(BaseModel):
    """Body of the ask endpoints."""

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    companies: list[str] | None = None

    @field_validator("companies")
    @classmethod
    def _known_companies(cls, v: list[str] | None) -> list[str] | None:
        unknown = [c for c in v or [] if c not in COMPANY_ALIASES]
        if unknown:
            raise ValueError(f"unknown companies: {unknown}")
        return v


# shortcut: per-process in-memory window; resets on restart, is not shared across workers and
# trusts X-Forwarded-For (spoofable if not behind a proxy). Move to Redis/edge limits on scale-out.
class RateLimiter:
    """Sliding-window limiter: `limit` hits per rolling hour per client key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Forget all recorded hits."""
        with self._lock:
            self._hits.clear()

    def check(self, key: str, limit: int) -> float | None:
        """Record a hit; return None if allowed, else seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return hits[0] + WINDOW_SECONDS - now
            hits.append(now)
        return None


limiter = RateLimiter()


def client_key(request: Request) -> str:
    """First X-Forwarded-For entry (proxy), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """One shared question budget per client across both ask endpoints.

    Called inside the endpoints (after body validation) so a rejected request costs nothing.
    """
    limit = get_settings().rate_limit_per_hour
    wait = limiter.check(client_key(request), limit)
    if wait is not None:
        seconds = max(1, math.ceil(wait))
        minutes = max(1, math.ceil(seconds / 60))
        unit = "minute" if minutes == 1 else "minutes"
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached: {limit} questions per hour. "
            f"Try again in {minutes} {unit}.",
            headers={"Retry-After": str(seconds)},
        )


def get_answer_fn() -> AnswerFn:
    """Dependency: the agent's answer function (override in tests)."""
    return agent.answer


def get_stream_fn() -> StreamFn:
    """Dependency: the agent's streaming function (override in tests)."""
    return agent.stream_answer


@app.exception_handler(groq.APIError)
@app.exception_handler(psycopg.Error)
async def _unavailable(request: Request, exc: Exception) -> JSONResponse:
    log.error("upstream failure on %s: %s", request.url.path, type(exc).__name__, exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": UNAVAILABLE})


@app.post("/api/ask")
def ask(
    body: AskRequest, request: Request, answer_fn: Annotated[AnswerFn, Depends(get_answer_fn)]
) -> AnswerResponse:
    """Answer a question with page-level citations."""
    rate_limit(request)
    response, _state = answer_fn(body.question, body.companies)
    return response


def _ndjson(events: Iterator[dict]) -> Iterator[str]:
    """One JSON line per event; a mid-stream failure becomes a single safe error event."""
    try:
        for event in events:
            yield json.dumps(event) + "\n"
    except Exception:
        log.exception("stream failed")
        yield json.dumps({"type": "error", "message": "Something went wrong. Please try again."})
        yield "\n"


@app.post("/api/ask/stream")
def ask_stream(
    body: AskRequest, request: Request, stream_fn: Annotated[StreamFn, Depends(get_stream_fn)]
) -> StreamingResponse:
    """Stream progress steps and the final answer as NDJSON."""
    rate_limit(request)
    return StreamingResponse(
        _ndjson(stream_fn(body.question, body.companies)), media_type="application/x-ndjson"
    )


@app.get("/api/companies")
def companies() -> list[str]:
    """Canonical company names."""
    return list(COMPANY_ALIASES)


@app.get("/api/health")
def health() -> JSONResponse:
    """Liveness plus database reachability."""
    try:
        ok = db.ping()
    except Exception:  # noqa: BLE001 - any failure means "not healthy"
        log.exception("health check failed")
        ok = False
    if ok:
        return JSONResponse({"status": "ok", "db": True})
    return JSONResponse({"status": "error", "db": False}, status_code=503)


# Frontend hooks: nothing is served until static/ (with index.html) exists at import time.
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_model=None)
def index() -> FileResponse | dict[str, str]:
    """Serve the frontend if it has been built."""
    page = STATIC_DIR / "index.html"
    return FileResponse(page) if page.is_file() else {"message": "Frontend not built yet"}
