"""Per-page digit cross-check: Docling parse cache vs plain pypdfium2 text. Detection only.

Usage: uv run python scripts/check_digits.py --company Infosys

Docling drops page headers/footers and text inside pictures, so its count is normally a bit
lower on every page. Each page's difference is measured against the report's median
difference; pages deviating by more than --tolerance digits are flagged.
"""

import argparse
import json
from pathlib import Path

import yaml

from finsight.ingest.parse import cache_path
from finsight.ingest.quality import digit_deviation


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--company", required=True)
    ap.add_argument("--tolerance", type=int, default=5)
    ap.add_argument("--manifest", default="config/manifest.yaml")
    args = ap.parse_args()

    reports = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))["reports"]
    report = next(r for r in reports if r["company"].lower() == args.company.lower())
    cache = cache_path(report["company"], report["fiscal_year"])
    data = json.loads(cache.read_text(encoding="utf-8"))
    rows = digit_deviation(data["elements"], Path(report["pdf"]))

    flagged = [r for r in rows if abs(r[3]) > args.tolerance]
    fewer = sum(r[3] < 0 for r in flagged)
    print(
        f"{report['company']}: {len(rows)} pages, docling digits {sum(r[1] for r in rows)}, "
        f"pdfium digits {sum(r[2] for r in rows)}"
    )
    print(
        f"flagged pages (|deviation| > {args.tolerance}): {len(flagged)} "
        f"({fewer} with fewer digits in Docling, {len(flagged) - fewer} with more)"
    )
    print("page | docling | pdfium | deviation")
    for p, d, f, dev in sorted(flagged, key=lambda r: -abs(r[3]))[:15]:
        print(f"{p} | {d} | {f} | {dev:+g}")


if __name__ == "__main__":
    main()
