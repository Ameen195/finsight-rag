"""Docling PDF parsing → flat list of elements with page numbers, cached as JSON.

Parsing runs in batches of BATCH_PAGES pages; each batch is cached, so an interrupted
run resumes where it stopped.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import pypdfium2
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel, DoclingDocument, SectionHeaderItem, TableItem

log = logging.getLogger(__name__)

PARSED_DIR = Path("data/parsed")
BATCH_PAGES = 30
TEXT_LABELS = {
    DocItemLabel.TEXT,
    DocItemLabel.PARAGRAPH,
    DocItemLabel.LIST_ITEM,
    DocItemLabel.CAPTION,
    DocItemLabel.FOOTNOTE,
}


def cache_path(company: str, fiscal_year: str) -> Path:
    """Where the parsed JSON for one report lives."""
    return PARSED_DIR / f"{company.lower().replace(' ', '_')}_{fiscal_year.lower()}.json"


def _converter(ocr: bool) -> DocumentConverter:
    opts = PdfPipelineOptions(do_ocr=ocr, do_table_structure=True)
    if ocr:
        # some PDFs have broken text layers (split/lost glyphs); read the rendered page instead
        opts.ocr_options = RapidOcrOptions(force_full_page_ocr=True, backend="torch")
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def to_elements(doc: DoclingDocument, pictures: bool = False) -> list[dict[str, Any]]:
    """Flatten a DoclingDocument into `{type, text, page}` dicts (tables also get `caption`).

    `iterate_items()` only walks the body layer, so page headers/footers are already excluded.
    With `pictures=True` it also yields text Docling placed inside pictures (KPI tiles,
    infographics, chart labels).
    """
    elements: list[dict[str, Any]] = []
    for item, _ in doc.iterate_items(traverse_pictures=pictures):
        if not getattr(item, "prov", None):
            continue
        page = item.prov[0].page_no
        if isinstance(item, SectionHeaderItem) or item.label == DocItemLabel.TITLE:
            elements.append({"type": "heading", "text": item.text.strip(), "page": page})
        elif isinstance(item, TableItem):
            md = item.export_to_markdown(doc=doc).strip()
            if md:
                caption = item.caption_text(doc).strip()
                elements.append({"type": "table", "text": md, "page": page, "caption": caption})
        elif item.label in TEXT_LABELS and item.text.strip():
            elements.append({"type": "text", "text": item.text.strip(), "page": page})
    return elements


def page_count(pdf: Path) -> int:
    """Number of pages in the PDF."""
    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def parse_report(
    pdf: Path,
    company: str,
    fiscal_year: str,
    ocr: bool = False,
    pictures: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Parse one PDF (or load the cache) → `{"pages", "ocr", "pictures", "elements"}`."""
    out = cache_path(company, fiscal_year)
    recovered: list[int] = []
    if out.exists():
        data = json.loads(out.read_text(encoding="utf-8"))
        settings_match = (data.get("ocr", False), data.get("pictures", False)) == (ocr, pictures)
        if settings_match and not force:
            log.info("Using cached parse %s", out)
            return data
        recovered = data.get("picture_pages", [])
        log.info("Re-parsing %s (force=%s, settings changed=%s)", out, force, not settings_match)

    n_pages = page_count(pdf)
    suffix = ("_ocr" if ocr else "") + ("_pics" if pictures else "")
    batch_dir = out.parent / f"{out.stem}{suffix}_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    converter: DocumentConverter | None = None
    elements: list[dict[str, Any]] = []
    for start in range(1, n_pages + 1, BATCH_PAGES):
        end = min(start + BATCH_PAGES - 1, n_pages)
        batch_file = batch_dir / f"{start:04d}-{end:04d}.json"
        if batch_file.exists() and not force:
            elements += json.loads(batch_file.read_text(encoding="utf-8"))
            continue
        converter = converter or _converter(ocr)
        t0 = time.time()
        doc = converter.convert(pdf, page_range=(start, end)).document
        batch = to_elements(doc, pictures)
        batch_file.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        elements += batch
        log.info(
            "%s: pages %d-%d of %d parsed in %.0fs (ocr=%s)",
            company,
            start,
            end,
            n_pages,
            time.time() - t0,
            ocr,
        )

    data = {"pages": n_pages, "ocr": ocr, "pictures": pictures, "elements": elements}
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if recovered and not pictures:
        # a fresh parse drops earlier picture-text recovery; redo it on the same pages
        log.warning(
            "%s: re-parse replaced %d picture-recovered pages; re-running recovery on them",
            company,
            len(recovered),
        )
        data = reparse_pages_with_pictures(company, fiscal_year, pdf, recovered)
    return data


def reparse_pages_with_pictures(
    company: str, fiscal_year: str, pdf: Path, pages: list[int]
) -> dict:
    """Re-parse only `pages` with picture text included and swap them into the cache.

    Contiguous pages are converted as one range. Only the merged cache file is updated (the
    per-batch files keep the original parse); recovered pages are listed in `picture_pages`.
    """
    out = cache_path(company, fiscal_year)
    data = json.loads(out.read_text(encoding="utf-8"))
    converter = _converter(data.get("ocr", False))
    runs: list[tuple[int, int]] = []
    for p in sorted(set(pages)):
        if runs and p == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], p)
        else:
            runs.append((p, p))
    new: list[dict[str, Any]] = []
    for start, end in runs:
        t0 = time.time()
        new += to_elements(converter.convert(pdf, page_range=(start, end)).document, True)
        log.info(
            "%s: pages %d-%d re-parsed with pictures in %.0fs",
            company,
            start,
            end,
            time.time() - t0,
        )
    replaced = set(pages)
    kept = [e for e in data["elements"] if e["page"] not in replaced]
    data["elements"] = sorted(kept + new, key=lambda e: e["page"])  # stable: keeps reading order
    data["picture_pages"] = sorted(replaced | set(data.get("picture_pages", [])))
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def bookmark_sections(pdf: Path) -> dict[int, list[str]]:
    """Map each 1-based page to the bookmark path in force on it ({} if no bookmarks)."""
    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        toc = []
        for b in doc.get_toc():
            dest = b.get_dest()
            index = dest.get_index() if dest else None
            toc.append((b.level, b.get_title(), index))
        return sections_by_page(toc, len(doc))
    finally:
        doc.close()


# "01_..." / "0001 TechM ..." sequence prefixes, "AR 2025" / "AR_2025", "*.pdf"
_FILENAME_LIKE = re.compile(r"^\d+_|^\d{3,}|AR[ _]20|\.pdf$", re.IGNORECASE)


def is_filename_like(title: str) -> bool:
    """Bookmarks named after source files ("04_336371_... AR 2025-26 BRSR R5") or bare numbers."""
    return bool(_FILENAME_LIKE.search(title)) or not any(ch.isalpha() for ch in title)


def sections_by_page(toc: list[tuple[int, str, int | None]], n_pages: int) -> dict[int, list[str]]:
    """Pure helper: `(level, title, 0-based page index)` bookmarks → `{page: [title path]}`.

    Bookmarks may be out of page order, so their paths are sorted by start page first.
    A filename-like bookmark contributes no section: its pages get only its real ancestors.
    """
    starts: list[tuple[int, list[str]]] = []
    stack: list[str | None] = []
    for level, title, index in toc:
        title = title.strip()
        stack = stack[:level] + [None if is_filename_like(title) else title]
        if index is not None and index >= 0:
            starts.append((index + 1, [t for t in stack if t]))
    starts.sort(key=lambda s: s[0])
    out: dict[int, list[str]] = {}
    current: list[str] = []
    i = 0
    for page in range(1, n_pages + 1):
        while i < len(starts) and starts[i][0] <= page:
            current = starts[i][1]
            i += 1
        if current:
            out[page] = current
    return out
