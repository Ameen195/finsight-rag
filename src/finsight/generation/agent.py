"""LangGraph agent: classify → decompose → retrieve → generate → verify_citations.

Low-relevance retrieval short-circuits to a refusal before the big model is called.
"""

import json
import logging
import time
from collections.abc import Iterator
from typing import TypedDict

import groq
from langgraph.graph import END, START, StateGraph

from finsight.config import get_settings
from finsight.generation import llm
from finsight.generation.citations import is_refusal, verify
from finsight.generation.prompts import REFUSAL, answer_messages, chunk_tag, classify_messages
from finsight.generation.tracing import current_trace_id, init_tracing, observe, root_span
from finsight.ingest.chunk import n_tokens
from finsight.models import AnswerResponse, RetrievedChunk
from finsight.retrieval.filters import COMPANY_ALIASES, Filters, extract_fiscal_years
from finsight.retrieval.retriever import resolve_filters, retrieve, stored_fiscal_years

log = logging.getLogger(__name__)

SINGLE_K = 5
PER_COMPANY_K = 3


class AgentState(TypedDict, total=False):
    """Typed state passed between graph nodes."""

    question: str
    user_companies: list[str]  # explicit filter from the UI/API, wins over everything
    filters: Filters
    question_type: str  # "single" | "comparison"
    sub_questions: list[dict]  # {"question": str, "companies": list[str]}
    chunks: list[RetrievedChunk]
    best_score: float | None
    draft_answer: str
    answer: str
    citations: list
    invalid_citations: list[str]
    refused: bool
    tokens: int


def _llm_classification(question: str) -> tuple[dict, int]:
    """Small-model JSON classification; one retry on Groq's JSON validation error."""
    s = get_settings()
    for attempt in (1, 2):
        try:
            text, used = llm.complete_with_usage(
                classify_messages(question), s.small_model, json_mode=True, max_tokens=200
            )
            return json.loads(text), used
        except (groq.BadRequestError, json.JSONDecodeError) as e:
            log.warning("classify attempt %d failed: %s", attempt, type(e).__name__)
    return {}, 0


def _normalise_years(values: list) -> list[str]:
    """LLM fiscal years ('FY2026', 'FY26', 2026, '2025-26') -> ['FY2026'] style."""
    return extract_fiscal_years(" ".join(f"FY{v}" if str(v).isdigit() else str(v) for v in values))


@observe(name="classify")
def classify(state: AgentState) -> AgentState:
    """Question type + filters: the deterministic extraction wins over the small model."""
    det = resolve_filters(state["question"])
    raw, used = _llm_classification(state["question"])
    llm_companies = [c for c in raw.get("companies", []) if c in COMPANY_ALIASES]
    companies = state.get("user_companies") or det.companies or llm_companies
    years = det.fiscal_years or [
        y for y in _normalise_years(raw.get("fiscal_years", [])) if y in stored_fiscal_years()
    ]
    qtype = "comparison" if len(companies) >= 2 else "single"
    return {
        "filters": Filters(companies=companies, fiscal_years=years),
        "question_type": qtype,
        "tokens": state.get("tokens", 0) + used,
    }


@observe(name="decompose")
def decompose(state: AgentState) -> AgentState:
    """Comparisons: the original question once per company (no LLM rewrite)."""
    q, f = state["question"], state["filters"]
    if state["question_type"] == "comparison":
        subs = [{"question": q, "companies": [c]} for c in f.companies]
    else:
        subs = [{"question": q, "companies": f.companies}]
    return {"sub_questions": subs}


def _interleave(groups: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    """Round-robin merge so a context-budget cut never drops a whole company."""
    out: list[RetrievedChunk] = []
    for i in range(max((len(g) for g in groups), default=0)):
        out += [g[i] for g in groups if i < len(g)]
    return out


@observe(name="retrieve")
def retrieve_node(state: AgentState) -> AgentState:
    """hybrid_rerank per sub-question with its company filter; dedupe; enforce token budget."""
    s, f = get_settings(), state["filters"]
    k = PER_COMPANY_K if state["question_type"] == "comparison" else SINGLE_K
    groups = [
        retrieve(
            sq["question"],
            "hybrid_rerank",
            Filters(companies=sq["companies"], fiscal_years=f.fiscal_years),
            k=k,
        )
        for sq in state["sub_questions"]
    ]
    seen: set[int] = set()
    chunks: list[RetrievedChunk] = []
    budget = s.max_context_tokens
    for c in _interleave(groups):
        if c.chunk.id in seen:
            continue
        cost = n_tokens(chunk_tag(c) + "\n" + c.chunk.content)
        if chunks and cost > budget:
            continue  # keep at least one chunk; skip ones that no longer fit
        seen.add(c.chunk.id)
        chunks.append(c)
        budget -= cost
    scores = [c.rerank_score for c in chunks if c.rerank_score is not None]
    return {"chunks": chunks, "best_score": max(scores) if scores else None}


def route_after_retrieve(state: AgentState) -> str:
    """Refuse early when nothing relevant was retrieved."""
    best, threshold = state.get("best_score"), get_settings().min_rerank_score
    if not state["chunks"] or (threshold is not None and (best is None or best < threshold)):
        return "refuse"
    return "generate"


@observe(name="refuse")
def refuse(state: AgentState) -> AgentState:
    """Standard refusal without calling the big model."""
    return {"answer": REFUSAL, "citations": [], "invalid_citations": [], "refused": True}


@observe(name="generate", as_type="generation")
def generate(state: AgentState) -> AgentState:
    """Big-model answer from the retrieved context."""
    text, used = llm.complete_with_usage(
        answer_messages(state["question"], state["chunks"]),
        get_settings().big_model,
        max_tokens=800,
    )
    return {"draft_answer": text.strip(), "tokens": state.get("tokens", 0) + used}


@observe(name="verify_citations")
def verify_citations(state: AgentState) -> AgentState:
    """Drop citations that match no retrieved chunk; no valid citation and no refusal → refuse."""
    draft = state["draft_answer"]
    if is_refusal(draft):
        return {"answer": REFUSAL, "citations": [], "invalid_citations": [], "refused": True}
    answer, citations, invalid = verify(draft, state["chunks"])
    if not citations:
        return {"answer": REFUSAL, "citations": [], "invalid_citations": invalid, "refused": True}
    return {
        "answer": answer,
        "citations": citations,
        "invalid_citations": invalid,
        "refused": False,
    }


def build_graph():  # noqa: ANN201 - LangGraph's compiled type is internal
    """Compile the agent graph."""
    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("decompose", decompose)
    g.add_node("retrieve", retrieve_node)
    g.add_node("refuse", refuse)
    g.add_node("generate", generate)
    g.add_node("verify_citations", verify_citations)
    g.add_edge(START, "classify")
    g.add_edge("classify", "decompose")
    g.add_edge("decompose", "retrieve")
    g.add_conditional_edges(
        "retrieve", route_after_retrieve, {"refuse": "refuse", "generate": "generate"}
    )
    g.add_edge("generate", "verify_citations")
    g.add_edge("verify_citations", END)
    g.add_edge("refuse", END)
    return g.compile()


_graph = None


@observe(name="answer")
def _run(question: str, companies: list[str] | None) -> tuple[AgentState, str | None]:
    global _graph
    _graph = _graph or build_graph()
    state = _graph.invoke({"question": question, "user_companies": companies or [], "tokens": 0})
    return state, current_trace_id()


def _response(state: AgentState, t0: float, trace_id: str | None) -> AnswerResponse:
    return AnswerResponse(
        answer=state["answer"],
        citations=state.get("citations", []),
        question_type=state.get("question_type", "single"),
        refused=state.get("refused", False),
        latency_ms=round((time.perf_counter() - t0) * 1000),
        trace_id=trace_id,
    )


def answer(question: str, companies: list[str] | None = None) -> tuple[AnswerResponse, AgentState]:
    """Answer a question; returns the API response and the final state (for debugging/evals)."""
    init_tracing()
    t0 = time.perf_counter()
    state, trace_id = _run(question, companies)
    return _response(state, t0, trace_id), state


def stream_answer(question: str, companies: list[str] | None = None) -> Iterator[dict]:
    """Yield a `step` event per finished graph node, then one final `answer` event."""
    global _graph
    init_tracing()
    t0 = time.perf_counter()
    _graph = _graph or build_graph()
    state: dict = {}
    initial = {"question": question, "user_companies": companies or [], "tokens": 0}
    with root_span("answer"):  # one trace per streamed answer, node spans nest under it
        for update in _graph.stream(initial, stream_mode="updates"):
            for node, delta in update.items():
                state.update(delta)
                yield {"type": "step", "step": node}
        trace_id = current_trace_id()
    response = _response(state, t0, trace_id)  # type: ignore[arg-type]
    yield {"type": "answer", **response.model_dump()}
