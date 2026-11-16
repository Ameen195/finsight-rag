import json
from pathlib import Path

import pytest

from finsight.ingest import parse


class FakeConverter:
    def convert(self, pdf: Path, page_range: tuple[int, int]) -> object:
        return type("Result", (), {"document": page_range})()


@pytest.fixture
def offline_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[int]]:
    """Run parse_report without Docling: 2 pages, one text element per page."""
    calls: list[list[int]] = []
    monkeypatch.setattr(parse, "PARSED_DIR", tmp_path)
    monkeypatch.setattr(parse, "page_count", lambda pdf: 2)
    monkeypatch.setattr(parse, "_converter", lambda ocr: FakeConverter())
    monkeypatch.setattr(
        parse,
        "to_elements",
        lambda doc, pictures=False: [
            {"type": "text", "text": f"p{p} pictures={pictures}", "page": p}
            for p in range(doc[0], doc[1] + 1)
        ],
    )
    real = parse.reparse_pages_with_pictures

    def spy(company: str, fy: str, pdf: Path, pages: list[int]) -> dict:
        calls.append(sorted(pages))
        return real(company, fy, pdf, pages)

    monkeypatch.setattr(parse, "reparse_pages_with_pictures", spy)
    return calls


def test_recovered_pages_survive_force_reparse(offline_parse: list[list[int]]) -> None:
    pdf = Path("x.pdf")
    parse.parse_report(pdf, "Infosys", "FY2026")
    parse.reparse_pages_with_pictures("Infosys", "FY2026", pdf, [2])
    data = parse.parse_report(pdf, "Infosys", "FY2026", force=True)
    assert offline_parse == [[2], [2]]  # manual recovery, then automatic redo after --force
    assert data["picture_pages"] == [2]
    assert [e["text"] for e in data["elements"]] == ["p1 pictures=False", "p2 pictures=True"]
    cached = json.loads(parse.cache_path("Infosys", "FY2026").read_text(encoding="utf-8"))
    assert cached == data
