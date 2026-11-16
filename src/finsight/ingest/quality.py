"""Extraction quality checks against the PDF text layer. Detection only — nothing is changed."""

import statistics
from pathlib import Path

import pypdfium2


def digits(text: str) -> int:
    """Number of digit characters in `text`."""
    return sum(ch.isdigit() for ch in text)


def table_digits(md: str) -> int:
    """Digits in a Markdown table, counting a cell repeated across a merged span only once."""
    total = 0
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        total += sum(digits(c) for i, c in enumerate(cells) if i == 0 or c != cells[i - 1])
    return total


def element_digits(el: dict) -> int:
    """Digits in one parsed element (table cells de-duplicated, caption included)."""
    body = table_digits(el["text"]) if el["type"] == "table" else digits(el["text"])
    return body + digits(el.get("caption", ""))


def digit_deviation(elements: list[dict], pdf: Path) -> list[tuple[int, int, int, float]]:
    """Per page: `(page, docling_digits, pdfium_digits, deviation)`.

    Docling drops headers/footers, so its count is normally a little lower on every page;
    `deviation` is each page's difference minus the report's median difference.
    """
    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        pdfium = [digits(doc[i].get_textpage().get_text_range()) for i in range(len(doc))]
    finally:
        doc.close()
    docling = [0] * len(pdfium)
    for el in elements:
        docling[el["page"] - 1] += element_digits(el)
    diffs = [d - f for d, f in zip(docling, pdfium, strict=True)]
    median = statistics.median(diffs)
    return [
        (i + 1, d, f, diff - median)
        for i, (d, f, diff) in enumerate(zip(docling, pdfium, diffs, strict=True))
    ]


def pages_with_fewer_digits(elements: list[dict], pdf: Path, tolerance: int = 5) -> list[int]:
    """Pages where Docling holds clearly fewer digits than the text layer (likely lost text)."""
    return [p for p, _, _, dev in digit_deviation(elements, pdf) if dev < -tolerance]
