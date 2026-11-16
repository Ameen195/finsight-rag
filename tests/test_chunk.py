import pytest

from finsight.ingest import chunk
from finsight.ingest.chunk import (
    MIN_TOKENS,
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    chunk_elements,
    compact_table,
    split_table,
)
from finsight.ingest.parse import sections_by_page


@pytest.fixture(autouse=True)
def whitespace_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests stay offline: count whitespace-separated words instead of loading bge's tokenizer."""
    monkeypatch.setattr(chunk, "n_tokens", lambda t: len(t.split()))
    monkeypatch.setattr(chunk, "token_counts", lambda ts: [len(t.split()) for t in ts])


def n(text: str) -> int:
    return len(text.split())


def text(t: str, page: int) -> dict:
    return {"type": "text", "text": t, "page": page}


def table(md: str, page: int, caption: str = "") -> dict:
    return {"type": "table", "text": md, "page": page, "caption": caption}


def big_table(rows: int) -> str:
    head = ["| Year | Revenue (₹ crore) | Headcount |", "|---|---|---|"]
    return "\n".join(head + [f"| FY{i} | {1000 + i} | {50000 + i} |" for i in range(rows)])


def words(prefix: str, k: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(k))


def test_compact_table_strips_padding_and_rules() -> None:
    md = "|  A   |  B  |\n|------|-----|\n|  1,234 | (5) |"
    assert compact_table(md) == "| A | B |\n| --- | --- |\n| 1,234 | (5) |"


def test_table_split_by_rows_with_title_and_header_repeated() -> None:
    md = big_table(300)
    lines = md.splitlines()
    parts = split_table(md, title="Revenue by year", max_tokens=200)
    assert len(parts) > 1
    rows_seen: list[str] = []
    for part in parts:
        p = part.splitlines()
        assert p[0] == "Revenue by year" and p[1:3] == lines[:2]
        rows_seen += p[3:]
    assert rows_seen == lines[2:]  # every row intact, in order, none duplicated


def test_tiny_last_table_fragment_merged() -> None:
    md = big_table(30)  # 9 tokens per row under the whitespace counter
    parts = split_table(md, max_tokens=100)
    assert all(n(p) >= chunk.TINY_TABLE_TOKENS for p in parts)
    assert sum(len(p.splitlines()) - 2 for p in parts) == 30


def test_text_windows_size_and_overlap() -> None:
    chunks, _ = chunk_elements([text(words("w", 1200), 1)], "TCS", "FY2026")
    assert len(chunks) >= 3
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert n(a.content) <= TARGET_TOKENS
        a_words, b_words = a.content.split(), b.content.split()
        shared = a_words[a_words.index(b_words[0]) :]
        assert b_words[: len(shared)] == shared  # b starts with a's tail
        assert len(shared) == OVERLAP_TOKENS


def test_chunks_never_span_a_page_break() -> None:
    els = [text(words("alpha", 350), 3), text(words("beta", 30), 4), text(words("gamma", 350), 5)]
    chunks, _ = chunk_elements(els, "TCS", "FY2026")
    expected_page = {"alpha": 3, "beta": 4, "gamma": 5}
    for c in chunks:
        prefixes = {w.rstrip("0123456789") for w in c.content.split()}
        assert len(prefixes) == 1  # one page's words only
        assert c.page == expected_page[prefixes.pop()]
    assert [c.page for c in chunks].count(4) == 1  # short page 4 kept as its own chunk


def test_tiny_tail_absorbed_into_last_window() -> None:
    chunks, _ = chunk_elements([text(words("w", TARGET_TOKENS + 20), 1)], "TCS", "FY2026")
    assert len(chunks) == 1 and n(chunks[0].content) == TARGET_TOKENS + 20


def test_tiny_chunks_dropped_unless_they_contain_digits() -> None:
    els = [text("Short note.", 1), text("Revenue ₹1,78,650 crore", 2)]
    chunks, dropped = chunk_elements(els, "TCS", "FY2026")
    assert [c.content for c in chunks] == ["Revenue ₹1,78,650 crore"] and dropped == 1
    assert MIN_TOKENS == 10


def test_bookmark_sections_label_chunks() -> None:
    els = [text(words("a", 100), 1), text(words("b", 100), 2)]
    chunks, _ = chunk_elements(els, "TCS", "FY2026", {1: ["Report"], 2: ["Report", "Risks"]})
    assert [(c.page, c.section) for c in chunks] == [(1, "Report"), (2, "Report > Risks")]


def test_no_bookmarks_means_no_section() -> None:
    chunks, _ = chunk_elements([text(words("a", 100), 1)], "TCS", "FY2026")
    assert chunks[0].section is None


def test_table_standalone_with_caption_or_preceding_title() -> None:
    els = [
        text(words("d", 100), 1),
        {"type": "heading", "text": "Reconciliation of revenue", "page": 2},
        table(big_table(10), 2),
        table(big_table(10), 2, caption="Table 4: Headcount"),
        text(words("d", 100), 2),
    ]
    chunks, _ = chunk_elements(els, "TCS", "FY2026")
    tables = [c for c in chunks if c.is_table]
    assert [t.content.splitlines()[0] for t in tables] == [
        "Reconciliation of revenue",
        "Table 4: Headcount",
    ]
    assert all("| Year" not in c.content for c in chunks if not c.is_table)


def test_title_needs_letters() -> None:
    els = [{"type": "text", "text": "-", "page": 1}, table(big_table(10), 1)]
    chunks, _ = chunk_elements(els, "TCS", "FY2026")
    assert chunks[0].content.startswith("| Year")


def test_tiny_table_folded_into_text() -> None:
    els = [text(words("e", 60), 1), table("| (₹ crore) |\n|---|\n| 12 |", 1)]
    chunks, _ = chunk_elements(els, "TCS", "FY2026")
    assert len(chunks) == 1 and not chunks[0].is_table and "12" in chunks[0].content


def test_filename_like_bookmarks_give_no_section() -> None:
    toc = [
        (0, "Integrated Report", 0),
        (0, "04_336371_Tech Mahindra AR 2025-26 BRSR R5", 1),
        (0, "02 HCL Tech AR_2025-26_CGR_DNV", 2),
        (0, "0001 TechM IR 2026_Non-Stat_Final_230626", 3),
        (0, "annual_report.PDF", 3),
        (0, "2", 4),
        (0, "Financial Statements", 5),
    ]
    assert sections_by_page(toc, 6) == {1: ["Integrated Report"], 6: ["Financial Statements"]}


def test_sections_by_page_sorts_out_of_order_bookmarks() -> None:
    toc = [(0, "Annexures", 4), (0, "Intro", 0), (1, "About", 1), (0, "Bad link", None)]
    assert sections_by_page(toc, 6) == {
        1: ["Intro"],
        2: ["Intro", "About"],
        3: ["Intro", "About"],
        4: ["Intro", "About"],
        5: ["Annexures"],
        6: ["Annexures"],
    }
