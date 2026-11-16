"""Prompts for classification and answer generation."""

from finsight.models import RetrievedChunk
from finsight.retrieval.filters import COMPANY_ALIASES

REFUSAL = "I don't have enough information in the annual reports to answer that."

CLASSIFY_SYSTEM = (
    "Classify a question about Indian IT companies' annual reports. Reply with JSON only: "
    '{"type": "single" | "comparison", "companies": [...], "fiscal_years": [...]}. '
    f"companies must be chosen from {list(COMPANY_ALIASES)}. "
    'fiscal_years use the form "FY2026" (FY2026 = financial year 2025-26). '
    '"comparison" means the question compares two or more companies. '
    "Use empty lists when nothing is mentioned."
)

ANSWER_SYSTEM = f"""You answer questions about Indian IT companies' annual reports.
Rules:
- Use ONLY the context below. Never use outside knowledge.
- Cite every factual claim with the tag of the chunk it comes from, exactly as written in the
  context, e.g. [TCS, FY2026, p.211]. Put the tag right after the claim.
- Keep numbers, units and currency exactly as written in the source (e.g. ₹ crore, ₹ Million,
  US$ million). Do not convert or round.
- If the context does not contain the answer, reply with exactly:
  "{REFUSAL}" and nothing else.
- For comparisons, give each company's figure with its own citation, then one line comparing them.
- Be concise: a few sentences at most."""


def chunk_tag(chunk: RetrievedChunk) -> str:
    """Citation tag for a chunk: [Company, FY, p.X]."""
    c = chunk.chunk
    return f"[{c.company}, {c.fiscal_year}, p.{c.page}]"


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Context block: each chunk preceded by its citation tag."""
    return "\n\n".join(f"{chunk_tag(c)}\n{c.chunk.content}" for c in chunks)


def answer_messages(question: str, chunks: list[RetrievedChunk]) -> list[dict[str, str]]:
    """Chat messages for the answer model."""
    user = f"Context:\n\n{format_context(chunks)}\n\nQuestion: {question}"
    return [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}]


def classify_messages(question: str) -> list[dict[str, str]]:
    """Chat messages for the classifier."""
    return [{"role": "system", "content": CLASSIFY_SYSTEM}, {"role": "user", "content": question}]
