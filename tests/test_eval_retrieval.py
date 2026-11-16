import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "eval"))
from eval_retrieval import (  # noqa: E402
    all_companies_covered,
    first_hit_rank,
    percentile,
    report,
    summarize,
)

REL = [{"company": "Infosys", "page": 33}, {"company": "Infosys", "page": 16}]


def test_first_hit_rank_with_tolerance() -> None:
    got = [("Infosys", 100), ("Wipro", 33), ("Infosys", 34), ("Infosys", 16)]
    assert first_hit_rank(got, REL, 0) == 4  # Wipro p.33 is the wrong company
    assert first_hit_rank(got, REL, 1) == 3  # p.34 is within ±1 of p.33
    assert first_hit_rank([("Infosys", 1)], REL, 1) is None


def test_summarize_hand_computed() -> None:
    m = summarize([1, 3, None, 7])
    assert m["hit@1"] == 0.25 and m["hit@5"] == 0.5
    assert m["mrr@10"] == pytest.approx((1 + 1 / 3 + 1 / 7) / 4)


def test_all_companies_covered() -> None:
    rel = [{"company": "Wipro", "page": 45}, {"company": "HCLTech", "page": 120}]
    assert all_companies_covered([("Wipro", 45), ("HCLTech", 120)], rel)
    assert not all_companies_covered([("Wipro", 45), ("HCLTech", 121)], rel)


def test_percentile_nearest_rank() -> None:
    assert percentile([10, 20, 30, 40], 50) == 20 and percentile([10, 20, 30, 40], 95) == 40


def test_report_separates_comparison_and_ranks_worst() -> None:
    def q(qid: str, typ: str, rank: int | None) -> dict:
        modes = {
            m: {
                "rank_tol0": rank,
                "rank_tol1": rank,
                "latency_ms": 10,
                "retrieved": [],
                "all_companies_covered": False,
            }
            for m in ("dense", "keyword", "hybrid", "hybrid_rerank")
        }
        return {"id": qid, "type": typ, "question": "", "relevant": [], "modes": modes}

    details = [q("q1", "fact", 1), q("q2", "table", None), q("q3", "comparison", 2)]
    out = report(details, tol=1)
    assert out["overall_tol0"]["dense"]["hit@1"] == 0.5  # q1, q2 only
    assert (
        out["comparison"]["dense"]["hit@5"] == 1.0
        and out["comparison"]["dense"]["all_companies@10"] == 0
    )
    assert out["worst5_hybrid_rerank"][0] == "q2"
