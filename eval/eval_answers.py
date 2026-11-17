"""Answer-quality eval: runs the full agent on the golden set; cheap code checks for most rows,
an LLM judge only for explanation and comparison rows. Resumable and token-budgeted.

Usage:
  uv run python eval/eval_answers.py [--limit N | --ids q001,q020] [--max-tokens 150000]
                                     [--delay 0] [--reuse-old] [--out-dir eval/results]

Every agent answer and judge verdict is appended to eval/results/answers_cache.jsonl with the
git commit it was produced at; rows already cached for the current commit are skipped, so a
stopped run resumes. Entries from another commit are ignored unless --reuse-old is passed.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import groq

from finsight.config import get_settings
from finsight.generation import agent, llm
from finsight.generation.citations import is_refusal
from finsight.retrieval.filters import extract_companies

CACHE = Path("eval/results/answers_cache.jsonl")
JUDGED_TYPES = {"explanation", "comparison"}
NUM_TOKEN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(crore|cr\b|million|mn\b)?", re.IGNORECASE)
STOP = {"the", "and", "for", "with", "from", "that", "this", "over", "into", "per", "its", "via"}

JUDGE_SYSTEM = (
    "You grade an answer produced from annual-report passages. Reply with JSON only: "
    '{"faithfulness": 0 or 1, "correctness": 0, 0.5 or 1, "reason": "<one short sentence>"}. '
    "faithfulness = 1 only if every factual claim in the answer is supported by the cited "
    "passages. correctness = 1 if the answer matches the expected answer (numbers must match; "
    "units may be written differently), 0.5 if partly right or incomplete, 0 if wrong or a refusal."
)


# ---------------- code checks ----------------
def _numbers(text: str) -> list[tuple[float, str]]:
    """(value, unit) pairs; unit is 'crore', 'million' or ''. Years like 2026 are skipped."""
    out = []
    for m in NUM_TOKEN.finditer(text):
        raw, unit = m.group(1).rstrip(",."), (m.group(2) or "").lower()
        digits = raw.replace(",", "")
        # a year has no thousands separator; "1,965" is a count
        if not digits or ("," not in raw and re.fullmatch(r"(19|20)\d{2}", digits)):
            continue
        unit = (
            "crore" if unit in ("crore", "cr") else "million" if unit in ("million", "mn") else ""
        )
        out.append((float(digits), unit))
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.0015 * max(abs(a), abs(b)), 1e-9)


def number_match(expected: str, answer: str) -> bool | None:
    """True if every key number of the expected answer appears in the answer.

    Key numbers come from the text outside parentheses (parentheses hold extra detail).
    Grouping is ignored (1,78,650 = 178,650); crore vs million is converted (1 crore = 10
    million). None if the expected answer has no number.
    """
    main = re.sub(r"\([^)]*\)", " ", expected)
    wanted = _numbers(main) or _numbers(expected)
    if not wanted:
        return None
    got = _numbers(answer)

    def found(v: float, unit: str) -> bool:
        for a, aunit in got:
            if _close(a, v):
                return True
            if {unit, aunit} == {"crore", "million"}:
                factor = 10 if unit == "crore" else 0.1  # expected crore -> answer million
                if _close(a, v * factor):
                    return True
        return False

    return all(found(v, u) for v, u in wanted)


def phrase_match(expected: str, answer: str, threshold: float = 0.6) -> bool:
    """For rows without numbers: share of expected content words present in the answer."""
    words = {
        w
        for w in re.findall(r"[a-z]{4,}", re.sub(r"\([^)]*\)", " ", expected).lower())
        if w not in STOP
    }
    if not words:
        return False
    low = answer.lower()
    return sum(w in low for w in words) / len(words) >= threshold


def citation_stats(citations: list[dict], retrieved: list[dict], golden: list[dict]) -> dict:
    """Counts of citations that are retrieved, and that hit a golden page (exact / +-1)."""
    got = {(c["company"], c["page"]) for c in retrieved}

    def hit(c: dict, tol: int) -> bool:
        return any(
            g["company"] == c["company"] and abs(g["page"] - c["page"]) <= tol for g in golden
        )

    return {
        "n": len(citations),
        "retrieved": sum((c["company"], c["page"]) in got for c in citations),
        "golden_exact": sum(hit(c, 0) for c in citations),
        "golden_pm1": sum(hit(c, 1) for c in citations),
    }


def score(row: dict, cached: dict) -> dict:
    """Code-check verdicts for one cached answer."""
    answer, refused = cached["answer"], cached["refused"]
    out: dict = {"refused": refused}
    if row["type"] == "unanswerable":
        out["correct"] = 1.0 if refused else 0.0
        return out
    nm = number_match(row["expected_answer"], answer)
    out["number_match"] = nm
    out["code_correct"] = (
        0.0
        if refused
        else float(nm if nm is not None else phrase_match(row["expected_answer"], answer))
    )
    out["citations"] = citation_stats(
        cached["citations"], cached["retrieved"], row["relevant_pages"]
    )
    judge = cached.get("judge")
    out["correct"] = judge["correctness"] if judge else out["code_correct"]
    return out


# ---------------- running ----------------
def git_commit() -> str:
    """Current commit hash (with '+dirty' if the tracked tree has changes)."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "-uno"], capture_output=True, text=True
    ).stdout
    return head + ("+dirty" if dirty.strip() else "")


def load_cache(commit: str, reuse_old: bool) -> dict[str, dict]:
    """Latest cached entry per question id, for this commit (or any, with reuse_old)."""
    out: dict[str, dict] = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                if reuse_old or e.get("commit") == commit:
                    out[e["id"]] = e
    return out


class TokenMeter:
    """Wraps llm.complete_with_usage to count tokens per model during one call."""

    def __init__(self) -> None:
        self.by_model: dict[str, int] = {}
        self._orig = llm.complete_with_usage

    def __enter__(self) -> "TokenMeter":
        def counted(messages, model, json_mode=False, max_tokens=1024):  # noqa: ANN001, ANN202
            text, used = self._orig(messages, model, json_mode, max_tokens)
            self.by_model[model] = self.by_model.get(model, 0) + used
            return text, used

        llm.complete_with_usage = counted
        return self

    def __exit__(self, *exc: object) -> None:
        llm.complete_with_usage = self._orig


def oracle_companies(row: dict) -> list[str] | None:
    """Golden companies for a question that names none (simulates picking it in the UI)."""
    return None if extract_companies(row["question"]) else row["companies"]


def answer_row(row: dict, companies: list[str] | None = None) -> dict:
    """Run the agent on one golden question; return the cache payload."""
    with TokenMeter() as meter:
        response, state = agent.answer(row["question"], companies)
    return {
        "user_companies": companies,
        "answer": response.answer,
        "refused": response.refused or is_refusal(response.answer),
        "citations": [
            {"company": c.company, "page": c.page, "text": c.text} for c in response.citations
        ],
        "retrieved": [
            {"company": c.chunk.company, "page": c.chunk.page} for c in state.get("chunks", [])
        ],
        "latency_ms": response.latency_ms,
        "tokens": meter.by_model,
    }


def judge_json(messages: list[dict[str, str]]) -> dict:
    """Small-model JSON call; one retry on Groq's JSON validation error; {} if both fail."""
    for _ in range(2):
        try:
            text, _used = llm.complete_with_usage(
                messages, get_settings().small_model, json_mode=True, max_tokens=400
            )
            return json.loads(text)
        except (groq.BadRequestError, json.JSONDecodeError):
            continue
    return {}


def judge_row(row: dict, cached: dict) -> dict:
    """LLM judge (small model, JSON): faithfulness, correctness and a short reason."""
    passages = (
        "\n\n".join(
            f"[{c['company']}, p.{c['page']}]\n{c['text'][:1500]}" for c in cached["citations"]
        )
        or "(no passages cited)"
    )
    user = (
        f"Question: {row['question']}\nExpected answer: {row['expected_answer']}\n"
        f"Answer: {cached['answer']}\n\nCited passages:\n{passages}"
    )
    messages = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]
    with TokenMeter() as meter:
        verdict = judge_json(messages)
    return {
        "faithfulness": int(verdict.get("faithfulness", 0) or 0),
        "correctness": float(verdict.get("correctness", 0) or 0),
        "reason": str(verdict.get("reason", "judge returned no verdict"))[:300],
        "tokens": meter.by_model,
    }


def run(
    rows: list[dict],
    commit: str,
    reuse_old: bool,
    max_tokens: int,
    delay: float,
    oracle: bool = False,
) -> dict[str, dict]:
    """Answer (and judge) rows not yet cached; stop before the big-model token budget.

    With `oracle`, rows whose question names no company get the golden companies as the
    explicit filter; a cached entry is reused only if it was made with the same filter.
    """
    cache = load_cache(commit, reuse_old)
    big = get_settings().big_model
    spent = 0
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        companies = oracle_companies(row) if oracle else None
        entry, changed = cache.get(row["id"]), False
        if entry is not None and entry.get("user_companies") != companies:
            entry = None
        if entry is None:
            if spent >= max_tokens:
                print(f"token budget reached ({spent} >= {max_tokens}); stopping, rerun to resume")
                break
            entry = {"id": row["id"], "commit": commit, **answer_row(row, companies)}
            changed = True
            spent += entry["tokens"].get(big, 0)
            if delay:
                time.sleep(delay)
        if row["type"] in JUDGED_TYPES and "judge" not in entry:
            entry, changed = {**entry, "judge": judge_row(row, entry)}, True
        if changed:  # append-only: the latest line per id wins when the cache is loaded
            with CACHE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            cache[row["id"]] = entry
        print(f"{row['id']} done ({row['type']})")
    return cache


# ---------------- reporting ----------------
def summarize(rows: list[dict], cache: dict[str, dict]) -> dict:
    """Metrics per company and per question type, plus token use."""
    scored = [(r, cache[r["id"]], score(r, cache[r["id"]])) for r in rows if r["id"] in cache]

    def group(items: list) -> dict:
        ans = [s for r, _, s in items if r["type"] != "unanswerable"]
        una = [s for r, _, s in items if r["type"] == "unanswerable"]
        cits = [s["citations"] for s in ans]
        n_cit = sum(c["n"] for c in cits)
        # a refusal makes no claims, so it is left out of faithfulness (it still scores 0 correct)
        judged = [e["judge"] for _, e, s in items if "judge" in e and not s["refused"]]
        return {
            "n": len(items),
            "correct": round(statistics.mean(s["correct"] for s in ans), 3) if ans else None,
            "false_refusals": sum(s["refused"] for s in ans),
            "refusal_acc_unanswerable": round(statistics.mean(s["correct"] for s in una), 3)
            if una
            else None,
            "citation_retrieved": round(sum(c["retrieved"] for c in cits) / n_cit, 3)
            if n_cit
            else None,
            "citation_golden_exact": round(sum(c["golden_exact"] for c in cits) / n_cit, 3)
            if n_cit
            else None,
            "citation_golden_pm1": round(sum(c["golden_pm1"] for c in cits) / n_cit, 3)
            if n_cit
            else None,
            "faithfulness": round(statistics.mean(j["faithfulness"] for j in judged), 3)
            if judged
            else None,
        }

    def key_company(r: dict) -> str:
        return "comparison" if r["type"] == "comparison" else r["companies"][0]

    by_company, by_type = {}, {}
    for item in scored:
        by_company.setdefault(key_company(item[0]), []).append(item)
        by_type.setdefault(item[0]["type"], []).append(item)
    tokens: dict[str, int] = {}
    for _, e, _ in scored:
        for src in (e["tokens"], e.get("judge", {}).get("tokens", {})):
            for m, t in src.items():
                tokens[m] = tokens.get(m, 0) + t
    lat = [e["latency_ms"] for _, e, _ in scored]
    return {
        "overall": group(scored),
        "by_company": {k: group(v) for k, v in sorted(by_company.items())},
        "by_type": {k: group(v) for k, v in sorted(by_type.items())},
        "tokens": tokens,
        "tokens_per_question": round(sum(tokens.values()) / max(len(scored), 1)),
        "latency_ms": {
            "p50": statistics.median(lat) if lat else 0,
            "p95": sorted(lat)[max(0, round(0.95 * len(lat)) - 1)] if lat else 0,
        },
        "rows": [
            {
                "id": r["id"],
                "type": r["type"],
                "question": r["question"],
                "expected": r["expected_answer"],
                "answer": e["answer"],
                **s,
                "judge": e.get("judge"),
            }
            for r, e, s in scored
        ],
    }


def to_markdown(summary: dict, commit: str) -> str:
    """Render the report."""
    cols = [
        "n",
        "correct",
        "false_refusals",
        "refusal_acc_unanswerable",
        "citation_retrieved",
        "citation_golden_exact",
        "citation_golden_pm1",
        "faithfulness",
    ]

    def table(block: dict) -> list[str]:
        lines = ["| group | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        for name, g in block.items():
            lines.append(
                f"| {name} | " + " | ".join("—" if g[c] is None else str(g[c]) for c in cols) + " |"
            )
        return lines

    md = [
        f"# Answer eval (commit {commit})",
        "",
        "correct = code check (numbers / phrases), or the LLM judge's correctness for "
        "explanation and comparison rows; refusal_acc_unanswerable = share of unanswerable "
        "rows refused.",
        "",
        "## Overall",
        "",
    ]
    md += table({"all": summary["overall"]})
    md += ["", "## By company", ""] + table(summary["by_company"])
    md += ["", "## By question type", ""] + table(summary["by_type"])
    md += [
        "",
        f"Tokens: {summary['tokens']} · per question {summary['tokens_per_question']} · "
        f"latency p50/p95 {summary['latency_ms']['p50']}/{summary['latency_ms']['p95']} ms "
        "(includes waits on the Groq rate limit)",
        "",
        "## Failed rows",
        "",
    ]
    for r in summary["rows"]:
        if r["correct"] < 1:
            why = (
                r["judge"]["reason"]
                if r.get("judge")
                else (
                    "refused"
                    if r["refused"] and r["type"] != "unanswerable"
                    else "did not refuse"
                    if r["type"] == "unanswerable"
                    else "expected figure not found"
                )
            )
            md.append(f"- **{r['id']}** ({r['type']}) {r['question']} — {why}")
    return "\n".join(md) + "\n"


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--golden", type=Path, default=Path("eval/golden_set.jsonl"))
    ap.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    ap.add_argument("--limit", type=int, help="only the first N golden rows")
    ap.add_argument("--ids", help="comma-separated question ids, e.g. q001,q020")
    ap.add_argument(
        "--max-tokens", type=int, default=150_000, help="big-model token budget per run"
    )
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait between questions")
    ap.add_argument(
        "--reuse-old", action="store_true", help="accept cache entries from other commits"
    )
    ap.add_argument(
        "--from-commit",
        help="re-score the cached answers of this commit (missing rows are answered and tagged "
        "with it); safer than --reuse-old when trial runs share the cache",
    )
    ap.add_argument(
        "--oracle-company",
        action="store_true",
        help="rows whose question names no company use the golden companies as the filter",
    )
    args = ap.parse_args()

    rows = [json.loads(x) for x in args.golden.read_text(encoding="utf-8").splitlines() if x]
    if args.ids:
        wanted = set(args.ids.split(","))
        rows = [r for r in rows if r["id"] in wanted]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        sys.exit("no golden rows selected")
    commit = args.from_commit or git_commit()
    cache = run(rows, commit, args.reuse_old, args.max_tokens, args.delay, args.oracle_company)
    summary = summarize(rows, cache)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "answers.json").write_text(
        json.dumps({"commit": commit, **summary}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = to_markdown(summary, commit)
    (args.out_dir / "answers.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
