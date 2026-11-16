import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "eval"))
import eval_retrieval  # noqa: E402
from finsight.retrieval.filters import Filters  # noqa: E402


def test_oracle_filter_replaces_companies_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        eval_retrieval, "resolve_filters", lambda q: Filters(companies=[], fiscal_years=["FY2026"])
    )
    q = {"question": "Total dividend per share for FY2026?", "companies": ["Infosys"]}
    assert eval_retrieval.question_filters(q, oracle=False) == Filters(fiscal_years=["FY2026"])
    assert eval_retrieval.question_filters(q, oracle=True) == Filters(
        companies=["Infosys"], fiscal_years=["FY2026"]
    )
