from finsight.generation.citations import is_refusal, verify
from finsight.generation.prompts import REFUSAL
from finsight.models import Chunk, RetrievedChunk


def rc(company: str, page: int, content: str = "x") -> RetrievedChunk:
    chunk = Chunk(id=page, company=company, fiscal_year="FY2026", page=page, content=content)
    return RetrievedChunk(chunk=chunk, rerank_score=1.0)


CHUNKS = [
    rc("TCS", 211, "Revenue recognised 2,67,022"),
    rc("HCLTech", 120),
    rc("Tech Mahindra", 22),
]


def test_valid_citation_kept_with_snippet() -> None:
    answer, cits, invalid = verify("Revenue was ₹2,67,022 crore [TCS, FY2026, p.211].", CHUNKS)
    assert answer == "Revenue was ₹2,67,022 crore [TCS, FY2026, p.211]."
    assert [(c.company, c.page) for c in cits] == [("TCS", 211)] and invalid == []
    assert cits[0].snippet.startswith("Revenue recognised")


def test_invalid_citation_removed_and_reported() -> None:
    answer, cits, invalid = verify("A [TCS, FY2026, p.212]. B [TCS, FY2026, p.211].", CHUNKS)
    assert answer == "A. B [TCS, FY2026, p.211]."
    assert invalid == ["TCS, FY2026, p.212"] and len(cits) == 1


def test_grouped_citations_and_format_variants() -> None:
    text = "X [HCLTech, FY 2026, page 120; Tech Mahindra, FY2026, p 22; Wipro, FY2026, p.5]"
    answer, cits, invalid = verify(text, CHUNKS)
    assert answer == "X [HCLTech, FY2026, p.120; Tech Mahindra, FY2026, p.22]"
    assert [c.company for c in cits] == ["HCLTech", "Tech Mahindra"] and invalid == [
        "Wipro, FY2026, p.5"
    ]


def test_full_width_brackets_normalised() -> None:
    answer, cits, _ = verify("Grew 9.6%【TCS, FY2026, p.211】.", CHUNKS)
    assert answer == "Grew 9.6%[TCS, FY2026, p.211]." and len(cits) == 1


def test_alias_company_name_matches_canonical() -> None:
    _, cits, _ = verify("Y [Tata Consultancy Services, FY2026, p.211]", CHUNKS)
    assert [(c.company, c.page) for c in cits] == [("TCS", 211)]


def test_non_citation_brackets_untouched() -> None:
    answer, cits, invalid = verify("See note [1] and [a].", CHUNKS)
    assert answer == "See note [1] and [a]." and cits == [] and invalid == []


def test_duplicate_citations_listed_once() -> None:
    _, cits, _ = verify("A [TCS, FY2026, p.211]. B [TCS, FY2026, p.211].", CHUNKS)
    assert len(cits) == 1


def test_is_refusal() -> None:
    assert is_refusal(REFUSAL) and is_refusal(f'"{REFUSAL}"')
    assert not is_refusal("Revenue was ₹2,67,022 crore [TCS, FY2026, p.211].")
