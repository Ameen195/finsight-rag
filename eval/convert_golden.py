"""Convert verified golden-set text files into eval/golden_set.jsonl. Deterministic, no invention.

Usage: uv run python eval/convert_golden.py eval/golden_verified_infosys.txt [more.txt ...]
       [--out eval/golden_set.jsonl] [--overwrite]

Input lines: `type | question | answer | company | pages | note` ('#' lines and blanks skipped).
- pages "33 (also 10, 16)" -> [33, 10, 16]; unanswerable rows use "-" -> [].
- Comparison rows name several companies ("Wipro, HCLTech") and label pages per company:
  "Wipro 45; HCLTech 120 (also 121)".
- fiscal_year comes from the company's single report in config/manifest.yaml.
Any field that cannot be parsed stops the conversion with the file and line number.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

TYPES = {"fact", "table", "comparison", "explanation", "unanswerable"}


class GoldenFormatError(ValueError):
    """A row in a verified golden file could not be parsed."""


def _pages(text: str, where: str) -> list[int]:
    nums = re.findall(r"\d+", text)
    if not nums or re.sub(r"[\d\s,()]|also", "", text):
        raise GoldenFormatError(f"{where}: cannot parse pages {text!r}")
    return [int(n) for n in nums]


def parse_row(line: str, where: str, fiscal_years: dict[str, str]) -> dict:
    """One input line -> golden-set dict without `id`."""
    fields = [f.strip() for f in line.split("|")]
    if len(fields) != 6:  # note may be empty, but its column must be there
        raise GoldenFormatError(f"{where}: expected 6 '|'-separated fields, got {len(fields)}")
    typ, question, answer, company_field, pages_field = fields[:5]
    if typ not in TYPES:
        raise GoldenFormatError(f"{where}: unknown type {typ!r}")
    if not question or not answer:
        raise GoldenFormatError(f"{where}: empty question or answer")
    companies = [c.strip() for c in company_field.split(",") if c.strip()]
    for c in companies:
        if c not in fiscal_years:
            raise GoldenFormatError(f"{where}: company {c!r} has no single report in the manifest")
    years = {fiscal_years[c] for c in companies}
    if len(years) != 1:
        raise GoldenFormatError(f"{where}: companies span several fiscal years {sorted(years)}")

    if typ == "unanswerable":
        if pages_field not in ("-", ""):
            raise GoldenFormatError(f"{where}: unanswerable row must have pages '-'")
        relevant: list[dict] = []
    elif len(companies) == 1:
        relevant = [{"company": companies[0], "page": p} for p in _pages(pages_field, where)]
    else:
        relevant = []
        for part in pages_field.split(";"):
            name = next((c for c in companies if part.strip().startswith(c)), None)
            if name is None:
                raise GoldenFormatError(
                    f"{where}: page group {part.strip()!r} names no listed company"
                )
            relevant += [
                {"company": name, "page": p} for p in _pages(part.strip()[len(name) :], where)
            ]
        missing = set(companies) - {r["company"] for r in relevant}
        if missing:
            raise GoldenFormatError(f"{where}: no pages for {sorted(missing)}")
    return {
        "question": question,
        "expected_answer": answer,
        "type": typ,
        "companies": companies,
        "fiscal_year": years.pop(),
        "relevant_pages": relevant,
    }


def convert(paths: list[Path], fiscal_years: dict[str, str]) -> list[dict]:
    """Parse all input files in order and number the rows q001, q002, ..."""
    rows: list[dict] = []
    for path in paths:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip() and not line.lstrip().startswith("#"):
                rows.append(parse_row(line, f"{path}:{n}", fiscal_years))
    return [{"id": f"q{i:03d}", **r} for i, r in enumerate(rows, start=1)]


def manifest_years(manifest: Path) -> dict[str, str]:
    """company -> fiscal_year, only for companies with exactly one report."""
    reports = yaml.safe_load(manifest.read_text(encoding="utf-8"))["reports"]
    names = [r["company"] for r in reports]
    return {r["company"]: r["fiscal_year"] for r in reports if names.count(r["company"]) == 1}


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("eval/golden_set.jsonl"))
    ap.add_argument("--manifest", type=Path, default=Path("config/manifest.yaml"))
    ap.add_argument("--overwrite", action="store_true", help="replace an existing output file")
    args = ap.parse_args()
    if args.out.exists() and not args.overwrite:
        sys.exit(f"{args.out} exists; pass --overwrite to replace it")
    try:
        rows = convert(args.inputs, manifest_years(args.manifest))
    except GoldenFormatError as e:
        sys.exit(f"STOPPED: {e}")
    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    by_type = {t: sum(r["type"] == t for r in rows) for t in sorted(TYPES)}
    print(f"wrote {len(rows)} questions to {args.out}: {by_type}")


if __name__ == "__main__":
    main()
