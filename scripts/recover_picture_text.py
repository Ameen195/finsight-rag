"""Re-parse pages where Docling lost digits, with picture text included, and update the cache.

Usage: uv run python scripts/recover_picture_text.py --company Infosys

Selects pages whose Docling digit count is clearly below the PDF text layer (see
scripts/check_digits.py), re-parses only those with traverse_pictures=True, and prints
per-page digit counts before and after.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import yaml

from finsight.ingest.parse import cache_path, reparse_pages_with_pictures
from finsight.ingest.quality import digit_deviation, pages_with_fewer_digits


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--company", required=True)
    ap.add_argument("--tolerance", type=int, default=5)
    ap.add_argument("--manifest", default="config/manifest.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    reports = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))["reports"]
    report = next(r for r in reports if r["company"].lower() == args.company.lower())
    company, fy, pdf = report["company"], report["fiscal_year"], Path(report["pdf"])
    before = json.loads(cache_path(company, fy).read_text(encoding="utf-8"))
    pages = pages_with_fewer_digits(before["elements"], pdf, args.tolerance)
    print(f"{company}: {len(pages)} pages with fewer digits than the text layer: {pages}")

    t0 = time.time()
    after = reparse_pages_with_pictures(company, fy, pdf, pages)
    seconds = time.time() - t0

    old = {p: (d, f, dev) for p, d, f, dev in digit_deviation(before["elements"], pdf)}
    new = {p: (d, dev) for p, d, _, dev in digit_deviation(after["elements"], pdf)}
    recovered = [p for p in pages if new[p][0] > old[p][0]]
    still_low = [p for p in pages if new[p][1] < -args.tolerance]
    print(f"\nre-parsed {len(pages)} pages in {seconds:.0f}s")
    print("page | docling before | docling after | pdfium")
    for p in pages:
        print(f"{p} | {old[p][0]} | {new[p][0]} | {old[p][1]}")
    print(f"\nrecovered digits on {len(recovered)} pages; still below tolerance: {still_low}")


if __name__ == "__main__":
    main()
