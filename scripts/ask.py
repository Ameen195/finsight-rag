"""Ask the agent from the command line.

Usage: uv run python scripts/ask.py "What was Infosys's revenue in FY2026?" ["another question" ...]
       [--companies TCS Infosys]
"""

import argparse

from finsight.generation.agent import answer
from finsight.generation.tracing import flush


def main() -> None:
    """CLI entry point: prints answer, citations, best rerank score, tokens and latency."""
    ap = argparse.ArgumentParser(description="Ask FinSight a question.")
    ap.add_argument("questions", nargs="+")
    ap.add_argument("--companies", nargs="*", help="restrict to these companies")
    args = ap.parse_args()
    for q in args.questions:
        resp, state = answer(q, args.companies)
        best = state.get("best_score")
        print(f"\nQ: {q}")
        print(f"type: {resp.question_type} | filters: {state['filters'].model_dump()}")
        print(f"A: {resp.answer}")
        for c in resp.citations:
            print(f"   - [{c.company}, {c.fiscal_year}, p.{c.page}]")
        draft = state.get("draft_answer", "")
        if resp.answer != draft and draft and state.get("refused"):
            print(f"   (model draft before citation check: {draft!r})")
        if state.get("invalid_citations"):
            print(f"   dropped invalid citations: {state['invalid_citations']}")
        print(
            f"best rerank score: {best:.3f}" if best is not None else "best rerank score: none",
            f"| chunks: {len(state.get('chunks', []))} | groq tokens: {state.get('tokens', 0)}"
            f" | latency: {resp.latency_ms} ms | trace: {resp.trace_id or '-'}",
        )
    flush()


if __name__ == "__main__":
    main()
