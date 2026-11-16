import pytest

from finsight.retrieval.filters import extract_companies, extract_filters, extract_fiscal_years


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What was Infosys's revenue?", ["Infosys"]),
        ("Infy headcount", ["Infosys"]),
        ("Tata Consultancy Services attrition", ["TCS"]),
        ("Compare attrition at Wipro and HCLTech.", ["Wipro", "HCLTech"]),
        ("HCL Technologies revenue", ["HCLTech"]),
        ("TechM margins vs Tech Mahindra peers", ["Tech Mahindra"]),
        ("What is the revenue from Mars?", []),
        ("Is wiproof a word?", []),  # word boundaries
    ],
)
def test_extract_companies(text: str, expected: list[str]) -> None:
    assert extract_companies(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("revenue in FY25", ["FY2025"]),
        ("revenue in FY2026", ["FY2026"]),
        ("FY 2026 and FY'25", ["FY2025", "FY2026"]),
        ("in 2025-26", ["FY2026"]),
        ("in 2025–26 (en dash)", ["FY2026"]),
        ("financial year 2024-2025", ["FY2025"]),
        ("fiscal 2026 dividend", ["FY2026"]),
        ("fiscal year 2026", ["FY2026"]),
        ("between 2020-2030", []),  # not a financial-year range
        ("on March 31, 2026", []),  # bare calendar year is not a fiscal year
    ],
)
def test_extract_fiscal_years(text: str, expected: list[str]) -> None:
    assert extract_fiscal_years(text) == expected


def test_extract_filters() -> None:
    f = extract_filters("Compare Wipro and Infy attrition in FY26")
    assert f.companies == ["Infosys", "Wipro"] and f.fiscal_years == ["FY2026"]
