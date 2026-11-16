"""Answer-presence check: do a candidate's key numbers appear in the stored chunks for its pages?

Usage: uv run python eval/check_answer_presence.py eval/golden_candidates_infosys.txt

Input lines: `type | question | expected answer | company | page(s) | note` ('#' = comment).
Key terms are the numbers in the expected answer. A row passes if every number appears in
some stored chunk whose page is within +/-TOLERANCE of a listed page. Detection only.
"""

import re
import sys
from pathlib import Path

import pypdfium2
import yaml

from finsight.db import connect

TOLERANCE = 1
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_rows(path: Path) -> list[dict]:
    """Read the pipe-separated candidates file."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        typ, question, answer, company, pages, *_ = (p.strip() for p in line.split("|"))
        rows.append(
            {
                "type": typ,
                "question": question,
                "answer": answer,
                "company": company,
                "pages": [int(p) for p in re.findall(r"\d+", pages)],
            }
        )
    return rows


def key_numbers(answer: str) -> list[str]:
    """Numbers in the expected answer, e.g. '₹1,78,650 crore' -> ['1,78,650']."""
    return [n.rstrip(",.") for n in NUMBER.findall(answer)]


def contains(text: str, number: str) -> bool:
    """True if `number` appears as a whole number (not inside a longer one)."""
    return re.search(rf"(?<![\d,.]){re.escape(number)}(?!\d|[,.]\d)", text) is not None


def main() -> None:
    """CLI entry point."""
    rows = [r for r in parse_rows(Path(sys.argv[1])) if r["type"] != "unanswerable"]
    manifest = yaml.safe_load(Path("config/manifest.yaml").read_text(encoding="utf-8"))
    pdfs = {m["company"]: m["pdf"] for m in manifest["reports"]}
    pdf_cache: dict[str, pypdfium2.PdfDocument] = {}
    passed = 0
    with connect() as conn:
        for i, r in enumerate(rows, start=1):
            pages = sorted({p + d for p in r["pages"] for d in range(-TOLERANCE, TOLERANCE + 1)})
            chunks = conn.execute(
                "select page, content from chunks where company = %s and page = any(%s)"
                " order by page, id",
                (r["company"], pages),
            ).fetchall()
            stored = "\n".join(c for _, c in chunks)
            nums = key_numbers(r["answer"])
            missing = [n for n in nums if not contains(stored, n)]
            ok = bool(nums) and not missing
            passed += ok
            print(f"\n[{'PASS' if ok else 'MISS'}] {i}. {r['question']}")
            print(
                f"   expected: {r['answer']} | pages {r['pages']} (+/-{TOLERANCE})"
                f" | key numbers {nums} | missing {missing}"
            )
            if ok:
                continue
            pdf_path = pdfs[r["company"]]
            pdf = pdf_cache.setdefault(pdf_path, pypdfium2.PdfDocument(pdf_path))
            layer = "\n".join(
                pdf[p - 1].get_textpage().get_text_range() for p in pages if 1 <= p <= len(pdf)
            )
            print(
                f"   in PDF text layer (pypdfium2, same pages): "
                f"{[n for n in missing if contains(layer, n)]} of {missing}"
            )
            for page, content in chunks:
                if page in r["pages"]:
                    print(f"   --- stored chunk p.{page} ---\n{content}\n")
    for pdf in pdf_cache.values():
        pdf.close()
    print(f"\n{passed}/{len(rows)} answerable rows pass")


if __name__ == "__main__":
    main()
