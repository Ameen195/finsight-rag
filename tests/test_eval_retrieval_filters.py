import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "eval"))
import eval_retrieval  # noqa: E402
from finsight.retrieval.filters import Filters  # noqa: E402


def test_comparison_retrieves_per_company_and_interleaves(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_retrieve(question, mode, filters, k):  # noqa: ANN001, ANN202
        calls.append(filters.companies)
        return [f"{filters.companies[0]}{i}" for i in range(k)]

    monkeypatch.setattr(eval_retrieval, "retrieve", fake_retrieve)
    q = {"question": "Compare A and B", "type": "comparison"}
    got = eval_retrieval.retrieve_for(q, "hybrid", Filters(companies=["A", "B"]))
    assert calls == [["A"], ["B"]]
    assert got[:4] == ["A0", "B0", "A1", "B1"] and len(got) == eval_retrieval.K
    # single questions keep one search with the full filter
    calls.clear()
    eval_retrieval.retrieve_for(
        {"question": "x", "type": "fact"}, "hybrid", Filters(companies=["A", "B"])
    )
    assert calls == [["A", "B"]]


def test_oracle_filter_replaces_companies_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        eval_retrieval, "resolve_filters", lambda q: Filters(companies=[], fiscal_years=["FY2026"])
    )
    q = {"question": "Total dividend per share for FY2026?", "companies": ["Infosys"]}
    assert eval_retrieval.question_filters(q, oracle=False) == Filters(fiscal_years=["FY2026"])
    assert eval_retrieval.question_filters(q, oracle=True) == Filters(
        companies=["Infosys"], fiscal_years=["FY2026"]
    )
