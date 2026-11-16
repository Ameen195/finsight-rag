import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "eval"))
from convert_golden import GoldenFormatError, convert, parse_row  # noqa: E402

YEARS = {"Infosys": "FY2026", "Wipro": "FY2026", "HCLTech": "FY2026"}


def test_pages_with_also_and_note() -> None:
    row = parse_row(
        "table | Revenue? | ₹1,78,650 crore | Infosys | 33 (also 10, 16) | consolidated",
        "f:1",
        YEARS,
    )
    assert row["relevant_pages"] == [
        {"company": "Infosys", "page": 33},
        {"company": "Infosys", "page": 10},
        {"company": "Infosys", "page": 16},
    ]
    assert row["fiscal_year"] == "FY2026" and row["companies"] == ["Infosys"]


def test_unanswerable_has_no_pages() -> None:
    row = parse_row(
        "unanswerable | Revenue from Mars? | NOT IN REPORT | Infosys | - |", "f:2", YEARS
    )
    assert row["relevant_pages"] == []


def test_comparison_pages_per_company() -> None:
    row = parse_row(
        "comparison | Attrition? | 12% vs 13% | Wipro, HCLTech "
        "| Wipro 45; HCLTech 120 (also 121) |",
        "f:3",
        YEARS,
    )
    assert row["relevant_pages"] == [
        {"company": "Wipro", "page": 45},
        {"company": "HCLTech", "page": 120},
        {"company": "HCLTech", "page": 121},
    ]


@pytest.mark.parametrize(
    "line",
    [
        "fact | Q? | A | Infosys | p.33 |",  # unparseable pages
        "fact | Q? | A | Infosys |  |",  # answerable without pages
        "trivia | Q? | A | Infosys | 33 |",  # unknown type
        "fact | Q? | A | Infy | 33 |",  # company not in manifest
        "fact | Q? | A | Infosys | 33",  # missing note column
        "fact | Q? | A | B | Infosys | 33 |",  # extra field (e.g. a '|' inside the answer)
        "comparison | Q? | A | Wipro, HCLTech | 45, 120 |",  # pages not labelled per company
        "unanswerable | Q? | NOT IN REPORT | Infosys | 33 |",  # unanswerable with pages
    ],
)
def test_unparseable_rows_stop(line: str) -> None:
    with pytest.raises(GoldenFormatError):
        parse_row(line, "f:9", YEARS)


def test_convert_numbers_rows_and_skips_comments(tmp_path: Path) -> None:
    f = tmp_path / "golden.txt"
    f.write_text(
        "# header\n\nfact | Q1? | A1 | Infosys | 10 |\nfact | Q2? | A2 | Infosys | 11 | note\n",
        encoding="utf-8",
    )
    rows = convert([f], YEARS)
    assert [r["id"] for r in rows] == ["q001", "q002"]
    assert rows[1]["expected_answer"] == "A2"
