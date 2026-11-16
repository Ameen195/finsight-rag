"""Agent-retrieval eval: Hit@1/Hit@5 of the chunks the agent actually passes to the answer model.

Runs the agent's classify -> decompose -> retrieve nodes (small-model calls only, no answer
generation) for every answerable golden question, so changes to decomposition or per-company
retrieval show up here (eval_retrieval.py calls the retriever directly and cannot see them).

Usage: uv run python eval/eval_agent_retrieval.py --out-dir eval/results/agent_retrieval/<name>
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eval_retrieval import first_hit_rank, percentile  # noqa: E402
from finsight.db import shared_connection  # noqa: E402
from finsight.generation import agent  # noqa: E402


def run_question(question: str) -> tuple[list[tuple[str, int]], int]:
    """(company, page) list in the agent's context order, and Groq tokens used."""
    state: agent.AgentState = {"question": question, "user_companies": [], "tokens": 0}
    for node in (agent.classify, agent.decompose, agent.retrieve_node):
        state.update(node(state))
    return [(c.chunk.company, c.chunk.page) for c in state["chunks"]], state["tokens"]


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--golden", type=Path, default=Path("eval/golden_set.jsonl"))
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    rows = [json.loads(x) for x in args.golden.read_text(encoding="utf-8").splitlines() if x]
    ingested = {r[0] for r in shared_connection().execute("select distinct company from chunks")}
    scored = [r for r in rows if r["relevant_pages"] and set(r["companies"]) <= ingested]

    details = []
    for r in scored:
        t0 = time.perf_counter()
        got, tokens = run_question(r["question"])
        rank = first_hit_rank(got, r["relevant_pages"], 0)
        details.append(
            {
                "id": r["id"],
                "rank_tol0": rank,
                "retrieved": got,
                "tokens": tokens,
                "latency_ms": round((time.perf_counter() - t0) * 1000),
            }
        )
    n = len(details)
    summary = {
        "n": n,
        "hit@1": sum(d["rank_tol0"] == 1 for d in details) / n,
        "hit@5": sum(d["rank_tol0"] is not None and d["rank_tol0"] <= 5 for d in details) / n,
        "small_model_tokens_per_question": round(sum(d["tokens"] for d in details) / n),
        "latency_p50_ms": percentile([d["latency_ms"] for d in details], 50),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "agent_retrieval.json").write_text(
        json.dumps({"summary": summary, "details": details}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary))
    print({d["id"]: d["rank_tol0"] for d in details})


if __name__ == "__main__":
    main()
