"""`finsight-ingest`: parse → chunk → embed → replace rows in Postgres, per report."""

import argparse
import logging
import re
import time
from collections import Counter
from pathlib import Path

import yaml

from finsight.db import replace_report
from finsight.ingest.chunk import chunk_elements, embedding_text, token_counts
from finsight.ingest.embed import embed_passages, get_model
from finsight.ingest.parse import bookmark_sections, parse_report
from finsight.models import Chunk

log = logging.getLogger(__name__)


def ingest_one(report: dict, force: bool) -> dict:
    """Ingest one manifest entry and return its summary stats."""
    t0 = time.time()
    company, fy = report["company"], report["fiscal_year"]
    pdf = Path(report["pdf"])
    data = parse_report(
        pdf, company, fy, report.get("ocr", False), report.get("pictures", False), force
    )
    elements = drop_elements(data["elements"], report.get("drop_element_regex"))
    elements = apply_glyph_map(elements, report.get("glyph_map", {}))
    chunks, dropped = chunk_elements(elements, company, fy, bookmark_sections(pdf))
    texts = [embedding_text(c) for c in chunks]
    replace_report(company, fy, chunks, embed_passages(texts))
    tokens = token_counts([c.content for c in chunks])
    # +2 for [CLS]/[SEP]: anything past max_seq_length is silently cut before embedding
    limit = get_model().max_seq_length
    over = [n + 2 > limit for n in token_counts(texts)]
    sections = Counter(c.section.split(" > ")[0] if c.section else "(none)" for c in chunks)
    return {
        "company": company,
        "pdf_pages": data["pages"],
        "pages_w_content": len({e["page"] for e in data["elements"]}),
        "chunks": len(chunks),
        "tables": sum(c.is_table for c in chunks),
        "dropped": dropped,
        "avg_tokens": round(sum(tokens) / max(len(tokens), 1)),
        "text_over_bge_limit": _pct(over, chunks, is_table=False),
        "table_over_bge_limit": _pct(over, chunks, is_table=True),
        "top_sections": len(sections),
        "seconds": round(time.time() - t0),
        "_largest_sections": sections.most_common(5),
    }


def drop_elements(elements: list[dict], pattern: str | None) -> list[dict]:
    """Drop elements whose WHOLE text matches `pattern` (e.g. OCR'd page-header logos).

    Case-sensitive (add `(?i)` to the pattern if needed). Applied at chunk time so the parse
    cache keeps the raw extraction.
    """
    if not pattern:
        return elements
    rx = re.compile(pattern)
    kept = [e for e in elements if not rx.fullmatch(e["text"].strip())]
    log.info("drop_element_regex %r: %d elements dropped", pattern, len(elements) - len(kept))
    return kept


def apply_glyph_map(elements: list[dict], glyph_map: dict[str, str]) -> list[dict]:
    """Replace mis-mapped font glyphs (e.g. Infosys' rupee sign extracted as '`').

    Applied at chunk time so the parse cache keeps the raw extraction.
    """
    if not glyph_map:
        return elements
    out = []
    replaced = 0
    for el in elements:
        el = dict(el)
        for field in ("text", "caption"):
            if field in el:
                for old, new in glyph_map.items():
                    replaced += el[field].count(old)
                    el[field] = el[field].replace(old, new)
        out.append(el)
    log.info("glyph map %s: %d replacements", glyph_map, replaced)
    return out


def _pct(over: list[bool], chunks: list[Chunk], is_table: bool) -> str:
    """Share of text (or table) chunks whose flag in `over` is set, as 'N%'."""
    flags = [o for o, c in zip(over, chunks, strict=True) if c.is_table == is_table]
    return f"{100 * sum(flags) / max(len(flags), 1):.1f}%"


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Ingest annual reports into Postgres.")
    ap.add_argument("--company", help="only ingest this company (as named in the manifest)")
    ap.add_argument("--force", action="store_true", help="re-parse even if a cache exists")
    ap.add_argument("--manifest", default="config/manifest.yaml")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    reports = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))["reports"]
    if args.company:
        reports = [r for r in reports if r["company"].lower() == args.company.lower()]
        if not reports:
            raise SystemExit(f"No report for company {args.company!r} in {args.manifest}")

    rows = [ingest_one(r, args.force) for r in reports]
    cols = [c for c in rows[0] if not c.startswith("_")]
    print("\n" + " | ".join(cols))
    for row in rows:
        print(" | ".join(str(row[c]) for c in cols))
    for row in rows:
        print(f"\n{row['company']}: 5 largest top-level sections (chunks)")
        for name, n in row["_largest_sections"]:
            print(f"  {n:5d}  {name[:90]}")
