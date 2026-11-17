import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "eval"))
import eval_answers as ea  # noqa: E402


@pytest.mark.parametrize(
    ("expected", "answer", "ok"),
    [
        ("₹1,78,650 crore", "Revenue was ₹178,650 crore [Infosys, FY2026, p.33].", True),
        ("₹2,67,021 crore", "₹ 267,021 crore", True),
        ("₹56,815 crore (₹568,154 million)", "₹568,154 million", True),  # crore -> million
        ("₹926,240 million", "₹92,624 crore", True),  # million -> crore
        ("9.6%", "grew 9.6% in FY 2026", True),
        ("₹110 per share (three interims of ₹11, special ₹46)", "₹110 per share", True),
        ("TCS ₹2,67,021 crore; HCLTech ₹1,30,144 crore", "TCS ₹2,67,021 crore only", False),
        ("12.6%", "attrition was 13.7%", False),
        ("₹1,78,650 crore", "₹1,78,651 crore", True),  # within rounding tolerance
        ("NOT IN REPORT", "anything", None),
    ],
)
def test_number_match(expected: str, answer: str, ok: bool | None) -> None:
    assert ea.number_match(expected, answer) is ok


def test_number_match_ignores_years() -> None:
    assert ea.number_match("₹48 per share for FY2026", "₹48.00 per share") is True


def test_number_match_bare_count_that_looks_like_a_year() -> None:
    assert ea.number_match("1,965", "Infosys has **1,965 active clients**[Infosys, p.10].") is True
    assert ea.number_match("1,965", "Infosys has 1,900 active clients.") is False


def test_refusals_left_out_of_faithfulness() -> None:
    row = {
        "id": "q1",
        "type": "comparison",
        "expected_answer": "A 1; B 2",
        "relevant_pages": [],
        "companies": ["A", "B"],
        "question": "Compare A and B",
    }
    base = {"citations": [], "retrieved": [], "latency_ms": 1, "tokens": {}}
    judge = {"faithfulness": 0, "correctness": 0.0, "reason": "no numbers", "tokens": {}}
    good = {
        **base,
        "answer": "A 1, B 2",
        "refused": False,
        "judge": {**judge, "faithfulness": 1, "correctness": 1.0},
    }
    refused = {**base, "answer": "I don't have enough information", "refused": True, "judge": judge}
    rows = [row, {**row, "id": "q2"}]
    s = ea.summarize(rows, {"q1": {"id": "q1", **good}, "q2": {"id": "q2", **refused}})
    assert s["overall"]["faithfulness"] == 1.0 and s["overall"]["correct"] == 0.5


def test_oracle_companies_only_when_question_names_none() -> None:
    assert ea.oracle_companies({"question": "Total dividend?", "companies": ["Infosys"]}) == [
        "Infosys"
    ]
    assert ea.oracle_companies({"question": "Infosys dividend?", "companies": ["Infosys"]}) is None


def test_phrase_match() -> None:
    exp = "Three interim dividends after each quarter, topped up with a final dividend"
    assert ea.phrase_match(
        exp, "TCS pays three interim dividends each quarter, topped up by a final dividend."
    )
    assert not ea.phrase_match(exp, "TCS buys back shares.")


def test_citation_stats() -> None:
    cits = [
        {"company": "TCS", "page": 36},
        {"company": "TCS", "page": 37},
        {"company": "TCS", "page": 99},
    ]
    retrieved = [{"company": "TCS", "page": 36}, {"company": "TCS", "page": 37}]
    golden = [{"company": "TCS", "page": 36}]
    assert ea.citation_stats(cits, retrieved, golden) == {
        "n": 3,
        "retrieved": 2,
        "golden_exact": 1,
        "golden_pm1": 2,
    }


def test_score_refusals_and_judge() -> None:
    una = {"type": "unanswerable", "expected_answer": "NOT IN REPORT", "relevant_pages": []}
    assert ea.score(una, {"answer": "x", "refused": True})["correct"] == 1.0
    assert ea.score(una, {"answer": "x", "refused": False})["correct"] == 0.0
    fact = {
        "type": "fact",
        "expected_answer": "12.1%",
        "relevant_pages": [{"company": "TCS", "page": 5}],
    }
    refused = ea.score(fact, {"answer": "x", "refused": True, "citations": [], "retrieved": []})
    assert refused["correct"] == 0.0 and refused["refused"]
    comp = {"type": "comparison", "expected_answer": "A 1; B 2", "relevant_pages": []}
    judged = {
        "answer": "A 1",
        "refused": False,
        "citations": [],
        "retrieved": [],
        "judge": {"correctness": 0.5, "faithfulness": 1, "reason": "B missing"},
    }
    assert ea.score(comp, judged)["correct"] == 0.5


def test_run_resumes_and_respects_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ea, "CACHE", tmp_path / "cache.jsonl")
    calls: list[str] = []

    def fake_answer(row: dict, companies: list[str] | None = None) -> dict:
        calls.append(row["id"])
        return {
            "answer": "₹1 crore",
            "refused": False,
            "citations": [],
            "retrieved": [],
            "latency_ms": 10,
            "tokens": {ea.get_settings().big_model: 100},
        }

    monkeypatch.setattr(ea, "answer_row", fake_answer)
    monkeypatch.setattr(
        ea,
        "judge_row",
        lambda row, entry: {"faithfulness": 1, "correctness": 1.0, "reason": "ok", "tokens": {}},
    )
    rows = [{"id": "q1", "type": "fact"}, {"id": "q2", "type": "comparison"}]

    ea.run(rows, "abc", reuse_old=False, max_tokens=10_000, delay=0)
    assert calls == ["q1", "q2"]
    ea.run(rows, "abc", reuse_old=False, max_tokens=10_000, delay=0)  # all cached: no new calls
    assert calls == ["q1", "q2"]
    ea.run(rows, "def", reuse_old=True, max_tokens=10_000, delay=0)  # old commit accepted
    assert calls == ["q1", "q2"]
    ea.run(rows, "def", reuse_old=False, max_tokens=10_000, delay=0)  # new commit: re-answer
    assert calls == ["q1", "q2", "q1", "q2"]
    last = {json.loads(x)["id"]: json.loads(x) for x in ea.CACHE.read_text().splitlines()}
    assert last["q2"]["judge"]["reason"] == "ok" and last["q1"]["commit"] == "def"


def test_run_oracle_reanswers_only_rows_without_a_named_company(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ea, "CACHE", tmp_path / "cache.jsonl")
    seen: list[tuple[str, list[str] | None]] = []

    def fake_answer(row: dict, companies: list[str] | None = None) -> dict:
        seen.append((row["id"], companies))
        return {
            "user_companies": companies,
            "answer": "",
            "refused": False,
            "citations": [],
            "retrieved": [],
            "latency_ms": 1,
            "tokens": {},
        }

    monkeypatch.setattr(ea, "answer_row", fake_answer)
    rows = [
        {"id": "q1", "type": "fact", "question": "Total dividend?", "companies": ["Infosys"]},
        {"id": "q2", "type": "fact", "question": "TCS revenue?", "companies": ["TCS"]},
    ]
    ea.run(rows, "abc", reuse_old=False, max_tokens=10_000, delay=0)
    ea.run(rows, "abc", reuse_old=False, max_tokens=10_000, delay=0, oracle=True)
    assert seen == [("q1", None), ("q2", None), ("q1", ["Infosys"])]


def test_run_stops_at_token_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ea, "CACHE", tmp_path / "cache.jsonl")
    big = ea.get_settings().big_model
    monkeypatch.setattr(
        ea,
        "answer_row",
        lambda row, companies=None: {
            "answer": "",
            "refused": False,
            "citations": [],
            "retrieved": [],
            "latency_ms": 1,
            "tokens": {big: 3000},
        },
    )
    rows = [{"id": f"q{i}", "type": "fact"} for i in range(5)]
    cache = ea.run(rows, "abc", reuse_old=False, max_tokens=5000, delay=0)
    assert sorted(cache) == ["q0", "q1"]  # stops once 6000 >= 5000 before the third answer
