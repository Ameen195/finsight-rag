import contextlib
import json

import pytest

from finsight.generation import agent
from finsight.generation.prompts import REFUSAL
from finsight.models import Chunk, RetrievedChunk
from finsight.retrieval.filters import Filters


def rc(company: str, page: int, score: float = 2.0) -> RetrievedChunk:
    chunk = Chunk(
        id=hash((company, page)) % 10**6,
        company=company,
        fiscal_year="FY2026",
        page=page,
        content=f"{company} attrition was 12% on page {page}",
    )
    return RetrievedChunk(chunk=chunk, rerank_score=score)


class FakeLLM:
    """Records calls; returns a classification for the small model, `answer` for the big one."""

    def __init__(self, answer: str, classification: dict | None = None) -> None:
        self.answer, self.classification, self.calls = answer, classification or {}, []

    def __call__(self, messages, model, json_mode=False, max_tokens=1024):  # noqa: ANN001, ANN204
        self.calls.append(model)
        if json_mode:
            return json.dumps(self.classification), 50
        return self.answer, 900


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Offline agent: fake LLM + fake retrieval; returns a setter for both."""
    calls: list[Filters] = []

    def setup(answer: str, results: dict[str, list[RetrievedChunk]], classification=None):  # noqa: ANN001, ANN202
        fake = FakeLLM(answer, classification)
        monkeypatch.setattr(agent.llm, "complete_with_usage", fake)

        def fake_retrieve(q, mode, filters, k):  # noqa: ANN001, ANN202
            calls.append(filters)
            key = filters.companies[0] if len(filters.companies) == 1 else "*"
            return results.get(key, [])[:k]

        monkeypatch.setattr(agent, "retrieve", fake_retrieve)
        monkeypatch.setattr(agent, "stored_fiscal_years", lambda: frozenset({"FY2026"}))
        monkeypatch.setattr(
            agent,
            "resolve_filters",
            lambda q: Filters(companies=[c for c in ("TCS", "Wipro", "HCLTech") if c in q]),
        )
        monkeypatch.setattr(agent, "init_tracing", lambda: False)
        monkeypatch.setattr(agent, "current_trace_id", lambda: None)
        monkeypatch.setattr(agent, "root_span", lambda name: contextlib.nullcontext())
        monkeypatch.setattr(agent, "_graph", None)
        return fake, calls

    return setup


def test_single_question_answer_with_valid_citation(wire) -> None:  # noqa: ANN001
    fake, _ = wire("Attrition was 12% [TCS, FY2026, p.40].", {"TCS": [rc("TCS", 40)]})
    resp, state = agent.answer("What was TCS attrition?")
    assert resp.answer == "Attrition was 12% [TCS, FY2026, p.40]."
    assert [(c.company, c.page) for c in resp.citations] == [("TCS", 40)]
    assert resp.question_type == "single" and state["tokens"] == 950 and not state["refused"]
    assert resp.refused is False and resp.citations[0].text == "TCS attrition was 12% on page 40"


def test_answer_without_valid_citation_becomes_refusal(wire) -> None:  # noqa: ANN001
    wire("Attrition was 12% [TCS, FY2026, p.99].", {"TCS": [rc("TCS", 40)]})
    resp, state = agent.answer("What was TCS attrition?")
    assert resp.answer == REFUSAL and resp.citations == [] and resp.refused
    assert state["invalid_citations"] == ["TCS, FY2026, p.99"]


def test_model_refusal_passes_through(wire) -> None:  # noqa: ANN001
    wire(REFUSAL, {"TCS": [rc("TCS", 40)]})
    resp, state = agent.answer("What is TCS's revenue from Mars?")
    assert resp.answer == REFUSAL and state["refused"]


def test_low_rerank_score_refuses_without_big_model(wire, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(agent.get_settings(), "min_rerank_score", -3.0)
    fake, _ = wire("should not be used", {"TCS": [rc("TCS", 40, score=-9.0)]})
    resp, state = agent.answer("What is TCS's revenue from Mars?")
    assert resp.answer == REFUSAL and state["best_score"] == -9.0
    assert agent.get_settings().big_model not in fake.calls


def test_low_score_refusal_off_by_default(wire) -> None:  # noqa: ANN001
    assert agent.get_settings().min_rerank_score is None
    fake, _ = wire("x [TCS, FY2026, p.40]", {"TCS": [rc("TCS", 40, score=-9.0)]})
    resp, _ = agent.answer("What was TCS attrition?")
    assert resp.citations and agent.get_settings().big_model in fake.calls


def test_no_chunks_refuses(wire) -> None:  # noqa: ANN001
    fake, _ = wire("should not be used", {})
    resp, _ = agent.answer("What was TCS attrition?")
    assert resp.answer == REFUSAL and agent.get_settings().big_model not in fake.calls


def test_comparison_retrieves_per_company(wire) -> None:  # noqa: ANN001
    results = {"Wipro": [rc("Wipro", 10), rc("Wipro", 11)], "HCLTech": [rc("HCLTech", 20)]}
    fake, calls = wire(
        "Wipro 12% [Wipro, FY2026, p.10]; HCLTech 13% [HCLTech, FY2026, p.20].", results
    )
    resp, state = agent.answer("Compare attrition at Wipro and HCLTech.")
    assert resp.question_type == "comparison"
    assert [f.companies for f in calls] == [["Wipro"], ["HCLTech"]]
    assert [c.chunk.company for c in state["chunks"]] == [
        "Wipro",
        "HCLTech",
        "Wipro",
    ]  # interleaved
    assert {c.company for c in resp.citations} == {"Wipro", "HCLTech"}


def test_classifier_fills_gaps_but_deterministic_wins(wire) -> None:  # noqa: ANN001
    # no company in the text: the classifier's companies are used (unknown names dropped)
    wire(
        "x [Wipro, FY2026, p.10]",
        {"Wipro": [rc("Wipro", 10)]},
        classification={"type": "single", "companies": ["Wipro", "Acme"], "fiscal_years": [2026]},
    )
    _, state = agent.answer("What was the attrition rate?")
    assert state["filters"] == Filters(companies=["Wipro"], fiscal_years=["FY2026"])
    # company named in the text: deterministic extraction wins over the classifier
    wire(
        "x [TCS, FY2026, p.40]",
        {"TCS": [rc("TCS", 40)]},
        classification={"type": "comparison", "companies": ["Wipro", "HCLTech"]},
    )
    _, state = agent.answer("What was TCS attrition?")
    assert state["filters"].companies == ["TCS"] and state["question_type"] == "single"


def test_stream_answer_yields_steps_then_answer(wire) -> None:  # noqa: ANN001
    wire("Attrition was 12% [TCS, FY2026, p.40].", {"TCS": [rc("TCS", 40)]})
    events = list(agent.stream_answer("What was TCS attrition?"))
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert steps == ["classify", "decompose", "retrieve", "generate", "verify_citations"]
    final = events[-1]
    assert final["type"] == "answer" and final["refused"] is False
    assert final["citations"][0]["page"] == 40 and final["latency_ms"] >= 0


def test_stream_answer_refusal_path(wire) -> None:  # noqa: ANN001
    wire("unused", {})
    events = list(agent.stream_answer("What was TCS attrition?"))
    assert [e["step"] for e in events[:-1]] == ["classify", "decompose", "retrieve", "refuse"]
    assert events[-1]["refused"] is True and events[-1]["answer"] == REFUSAL


def test_user_company_filter_wins(wire) -> None:  # noqa: ANN001
    wire("x [HCLTech, FY2026, p.20]", {"HCLTech": [rc("HCLTech", 20)]})
    _, state = agent.answer("What was TCS attrition?", companies=["HCLTech"])
    assert state["filters"].companies == ["HCLTech"]
