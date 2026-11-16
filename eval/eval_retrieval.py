"""Retrieval eval: Hit@1, Hit@5, MRR@10 and latency for the 4 retrieval modes.

Usage: uv run python eval/eval_retrieval.py [--golden eval/golden_set.jsonl]
       [--out-dir eval/results] [--tolerance 1]

A hit is a retrieved chunk whose company matches a relevant page's company and whose page is
within the tolerance. Headline numbers use tolerance 0 (chunks are page-exact); +/-1 is
reported as secondary. Only answerable questions whose companies are all ingested are scored.
Comparison questions are reported separately (single-query retrieval, no decomposition yet).
"""

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from finsight.config import get_settings
from finsight.db import shared_connection
from finsight.retrieval.filters import Filters
from finsight.retrieval.retriever import MODES, resolve_filters, retrieve

K = 10


def first_hit_rank(retrieved: list[tuple[str, int]], relevant: list[dict], tol: int) -> int | None:
    """1-based rank of the first retrieved (company, page) matching a relevant page, else None."""
    for rank, (company, page) in enumerate(retrieved, start=1):
        if any(r["company"] == company and abs(r["page"] - page) <= tol for r in relevant):
            return rank
    return None


def summarize(ranks: list[int | None]) -> dict[str, float]:
    """Hit@1, Hit@5, MRR@10 over a list of first-hit ranks."""
    n = max(len(ranks), 1)
    return {
        "hit@1": sum(r == 1 for r in ranks) / n,
        "hit@5": sum(r is not None and r <= 5 for r in ranks) / n,
        "mrr@10": sum(1 / r for r in ranks if r is not None and r <= K) / n,
    }


def all_companies_covered(retrieved: list[tuple[str, int]], relevant: list[dict]) -> bool:
    """Comparison metric: every company in the question has a page-exact hit in the top K."""
    companies = {r["company"] for r in relevant}
    return all(
        first_hit_rank(retrieved, [r for r in relevant if r["company"] == c], 0) for c in companies
    )


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100)."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(p / 100 * len(s)) - 1))] if s else 0.0


def question_filters(q: dict, oracle: bool) -> Filters:
    """Filters from the question text; with `oracle`, the golden companies replace the extracted
    ones (simulates a user picking the company in the UI; diagnostic only)."""
    f = resolve_filters(q["question"])
    return f.model_copy(update={"companies": q["companies"]}) if oracle else f


def run(questions: list[dict], tol: int, oracle: bool = False) -> dict:
    """Retrieve for every question and mode; return per-question details."""
    for mode in MODES:  # warm-up: load models and open the DB connection outside the timing
        retrieve(questions[0]["question"], mode, k=K)
    details = []
    for q in questions:
        filters = question_filters(q, oracle)
        row = {
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "relevant": q["relevant_pages"],
            "modes": {},
        }
        for mode in MODES:
            t0 = time.perf_counter()
            res = retrieve(q["question"], mode, filters, k=K)
            ms = (time.perf_counter() - t0) * 1000
            got = [(r.chunk.company, r.chunk.page) for r in res]
            row["modes"][mode] = {
                "latency_ms": round(ms),
                "retrieved": got,
                "rank_tol0": first_hit_rank(got, q["relevant_pages"], 0),
                f"rank_tol{tol}": first_hit_rank(got, q["relevant_pages"], tol),
                "all_companies_covered": all_companies_covered(got, q["relevant_pages"]),
            }
        details.append(row)
    return {"details": details}


def report(details: list[dict], tol: int) -> dict:
    """Aggregate metrics: overall (non-comparison), comparison, per type, latency, worst 5."""
    single = [d for d in details if d["type"] != "comparison"]
    comparison = [d for d in details if d["type"] == "comparison"]
    out: dict = {
        "overall_tol0": {},
        f"overall_tol{tol}": {},
        "comparison": {},
        "by_type": {},
        "latency_ms": {},
    }
    for mode in MODES:
        out["overall_tol0"][mode] = summarize([d["modes"][mode]["rank_tol0"] for d in single])
        out[f"overall_tol{tol}"][mode] = summarize(
            [d["modes"][mode][f"rank_tol{tol}"] for d in single]
        )
        if comparison:
            stats = summarize([d["modes"][mode]["rank_tol0"] for d in comparison])
            stats["all_companies@10"] = statistics.mean(
                d["modes"][mode]["all_companies_covered"] for d in comparison
            )
            out["comparison"][mode] = stats
        lat = [d["modes"][mode]["latency_ms"] for d in details]
        out["latency_ms"][mode] = {"p50": percentile(lat, 50), "p95": percentile(lat, 95)}
    for typ in sorted({d["type"] for d in details}):
        group = [d for d in details if d["type"] == typ]
        out["by_type"][typ] = {
            "n": len(group),
            **{m: summarize([d["modes"][m]["rank_tol0"] for d in group]) for m in MODES},
        }

    def reciprocal_rank(d: dict) -> float:
        rank = d["modes"]["hybrid_rerank"]["rank_tol0"]
        return 1 / rank if rank else 0.0

    out["worst5_hybrid_rerank"] = [d["id"] for d in sorted(details, key=reciprocal_rank)[:5]]
    return out


def to_markdown(summary: dict, details: list[dict], meta: dict, tol: int) -> str:
    """Render the results as a Markdown report."""

    def table(block: dict, cols: list[str]) -> list[str]:
        lines = ["| mode | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        lines += [
            f"| {m} | " + " | ".join(f"{block[m][c]:.3f}" for c in cols) + " |" for m in block
        ]
        return lines

    md = [
        f"# Retrieval eval ({meta['date']})",
        "",
        f"Golden file: `{meta['golden']}` · questions scored: {meta['scored']} "
        f"(comparison: {meta['comparison']}) · skipped: {meta['skipped']} · "
        f"companies: {', '.join(meta['companies'])} · k={K}",
        "",
        f"Company filter: **{meta['filters']}** · RRF keyword weight: "
        f"**{meta['rrf_keyword_weight']}** · candidate pool: **{meta['candidate_pool']}** · "
        f"keyword OR-fallback pruning: **{meta['keyword_fallback_prune']}**",
        "",
        "## Headline: page tolerance 0 (non-comparison questions)",
        "",
    ]
    md += table(summary["overall_tol0"], ["hit@1", "hit@5", "mrr@10"])
    md += ["", f"## Secondary: page tolerance ±{tol}", ""]
    md += table(summary[f"overall_tol{tol}"], ["hit@1", "hit@5", "mrr@10"])
    if summary["comparison"]:
        md += ["", "## Comparison questions (tolerance 0, single query, no decomposition)", ""]
        md += table(summary["comparison"], ["hit@1", "hit@5", "mrr@10", "all_companies@10"])
    md += ["", "## Latency per query (ms)", ""]
    if meta.get("latency_note"):
        md += [f"*{meta['latency_note']}*", ""]
    md += ["| mode | p50 | p95 |", "|---|---|---|"]
    md += [f"| {m} | {v['p50']:.0f} | {v['p95']:.0f} |" for m, v in summary["latency_ms"].items()]
    md += [
        "",
        "## By question type (tolerance 0): Hit@5 / MRR@10",
        "",
        "| type | n | " + " | ".join(MODES) + " |",
        "|---|---|" + "---|" * len(MODES),
    ]
    for typ, block in summary["by_type"].items():
        cells = [f"{block[m]['hit@5']:.2f} / {block[m]['mrr@10']:.2f}" for m in MODES]
        md.append(f"| {typ} | {block['n']} | " + " | ".join(cells) + " |")
    md += ["", "## 5 worst questions (hybrid_rerank, tolerance 0)", ""]
    by_id = {d["id"]: d for d in details}
    for qid in summary["worst5_hybrid_rerank"]:
        d = by_id[qid]
        rel = ", ".join(f"{r['company']} p.{r['page']}" for r in d["relevant"])
        got = ", ".join(f"{c} p.{p}" for c, p in d["modes"]["hybrid_rerank"]["retrieved"][:5])
        md.append(f"- **{qid}** ({d['type']}) {d['question']}  \n  relevant: {rel} · top-5: {got}")
    return "\n".join(md) + "\n"


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--golden", type=Path, default=Path("eval/golden_set.jsonl"))
    ap.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    ap.add_argument("--tolerance", type=int, default=1, help="secondary page tolerance")
    ap.add_argument("--latency-note", default="", help="e.g. 'measured under load'")
    ap.add_argument(
        "--oracle-companies",
        action="store_true",
        help="diagnostic: filter by the golden companies instead of names found in the question",
    )
    args = ap.parse_args()
    if not args.golden.exists():
        sys.exit(f"{args.golden} not found: build it with eval/convert_golden.py (verified file)")

    rows = [
        json.loads(line) for line in args.golden.read_text(encoding="utf-8").splitlines() if line
    ]
    ingested = {r[0] for r in shared_connection().execute("select distinct company from chunks")}
    scored = [r for r in rows if r["relevant_pages"] and set(r["companies"]) <= ingested]
    if not scored:
        sys.exit("no answerable questions for the ingested companies")
    details = run(scored, args.tolerance, args.oracle_companies)["details"]
    summary = report(details, args.tolerance)
    meta = {
        "date": date.today().isoformat(),
        "golden": str(args.golden),
        "scored": len(scored),
        "comparison": sum(r["type"] == "comparison" for r in scored),
        "skipped": len(rows) - len(scored),
        "companies": sorted({c for r in scored for c in r["companies"]}),
        "latency_note": args.latency_note,
        "filters": "golden companies (oracle, diagnostic)"
        if args.oracle_companies
        else "extracted from the question",
        "rrf_keyword_weight": get_settings().rrf_keyword_weight,
        "candidate_pool": get_settings().retrieval_top_k,
        "keyword_fallback_prune": get_settings().keyword_fallback_prune,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "retrieval.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "details": details}, indent=2),
        encoding="utf-8",
    )
    md = to_markdown(summary, details, meta, args.tolerance)
    (args.out_dir / "retrieval.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
