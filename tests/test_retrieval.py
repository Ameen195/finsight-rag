import pytest

from finsight.models import Chunk, RetrievedChunk
from finsight.retrieval import retriever
from finsight.retrieval.filters import Filters
from finsight.retrieval.hybrid import rrf
from finsight.retrieval.keyword import or_query, prune_or_terms


def item(id_: int, **scores: float) -> RetrievedChunk:
    chunk = Chunk(id=id_, company="Infosys", fiscal_year="FY2026", page=id_, content=f"c{id_}")
    return RetrievedChunk(chunk=chunk, **scores)


def test_rrf_hand_computed() -> None:
    dense = [item(1, dense_score=0.9), item(2, dense_score=0.8), item(3, dense_score=0.7)]
    keyword = [item(3, keyword_score=5.0), item(1, keyword_score=4.0), item(4, keyword_score=1.0)]
    fused = rrf([dense, keyword], k=60)
    # 1: 1/61 + 1/62 = 0.032523   3: 1/63 + 1/61 = 0.032266
    # 2: 1/62 = 0.016129          4: 1/63 = 0.015873
    assert [f.chunk.id for f in fused] == [1, 3, 2, 4]
    assert fused[0].rrf_score == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1].rrf_score == pytest.approx(1 / 63 + 1 / 61)
    assert (fused[0].dense_score, fused[0].keyword_score) == (0.9, 4.0)  # both scores kept
    assert fused[2].keyword_score is None


def test_weighted_rrf_hand_computed() -> None:
    dense = [item(1), item(2)]
    keyword = [item(2), item(3)]
    fused = rrf([dense, keyword], k=60, weights=[1.0, 0.5])
    # 2: 1/62 + 0.5/61 = 0.024326   1: 1/61 = 0.016393   3: 0.5/62 = 0.008065
    assert [f.chunk.id for f in fused] == [2, 1, 3]
    assert fused[0].rrf_score == pytest.approx(1 / 62 + 0.5 / 61)
    assert fused[2].rrf_score == pytest.approx(0.5 / 62)


@pytest.mark.parametrize(
    ("strict", "loose"),
    [
        ("'revenu' & 'infosi'", "'revenu' | 'infosi'"),
        ("'revenu' & '1' <-> '78' <-> '650'", "'revenu' | '1' <-> '78' <-> '650'"),  # phrase kept
        ("'revenu'", None),  # single term: nothing to loosen
        ("'revenu' & !'mar'", None),  # negation would match almost everything
        ("", None),  # only stop words
    ],
)
def test_or_query(strict: str, loose: str | None) -> None:
    assert or_query(strict) == loose


@pytest.mark.parametrize(
    ("loose", "expected"),
    [
        (
            "'buyback' | 'infosi' | 'complet' | 'size' | 'price' | 'per' | 'share'",
            "'buyback' | 'complet' | 'size'",
        ),
        ("'much' | 'infosi' | 'spend' | 'csr' | 'fiscal' | '2026'", "'spend' | 'csr'"),
        ("'revenu' | 'fy2026' | '1' <-> '78' <-> '650'", "'revenu' | '1' <-> '78' <-> '650'"),
        ("'infosi' | 'fiscal'", None),  # nothing useful left
        ("'revenu' | '23'", "'revenu' | '23'"),  # a 2-digit number is not a year
    ],
)
def test_prune_or_terms(loose: str, expected: str | None) -> None:
    drop = frozenset({"infosi", "per", "share", "price", "much", "fiscal", "global"})
    assert prune_or_terms(loose, drop) == expected


def test_unknown_fiscal_year_is_not_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriever, "stored_fiscal_years", lambda: frozenset({"FY2026"}))
    assert retriever.resolve_filters("Infosys revenue in FY2025") == Filters(
        companies=["Infosys"], fiscal_years=[]
    )
    assert retriever.resolve_filters("Infosys revenue in FY26").fiscal_years == ["FY2026"]


def test_hybrid_rerank_pipeline_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriever, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(retriever.dense, "search", lambda v, k, f: [item(1), item(2)])
    monkeypatch.setattr(retriever.keyword, "search", lambda q, k, f: [item(2), item(3)])
    monkeypatch.setattr(retriever, "rerank", lambda q, cs: sorted(cs, key=lambda c: -c.chunk.id))
    f = Filters()
    assert [r.chunk.id for r in retriever.retrieve("q", "hybrid", f, k=3)] == [2, 1, 3]
    assert [r.chunk.id for r in retriever.retrieve("q", "hybrid_rerank", f, k=2)] == [3, 2]
    # rerank only the fused top-2 ([2, 1] -> [2, 1] by -id); chunk 3 stays behind in RRF order
    monkeypatch.setattr(retriever.get_settings(), "rerank_candidates", 2)
    assert [r.chunk.id for r in retriever.retrieve("q", "hybrid_rerank", f, k=3)] == [2, 1, 3]
