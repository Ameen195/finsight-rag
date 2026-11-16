"""Deterministic citation parsing and verification against the retrieved chunks."""

import re

from finsight.generation.prompts import REFUSAL
from finsight.models import Citation, RetrievedChunk
from finsight.retrieval.filters import extract_companies

_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_BRACKET_VARIANTS = str.maketrans({"【": "[", "】": "]", "［": "[", "］": "]"})
# one citation inside a bracket group: "TCS, FY2026, p.211" (also "page 211", "p 211")
_ONE = re.compile(r"^\s*(.+?)\s*,\s*(FY\s?\d{4})\s*,\s*p(?:age|g)?\.?\s*(\d+)\s*$", re.IGNORECASE)

Key = tuple[str, str, int]


def is_refusal(text: str) -> bool:
    """True if the answer is the standard refusal."""
    return text.strip().strip('"').startswith(REFUSAL)


def _key(company: str, fy: str, page: str) -> Key:
    canonical = extract_companies(company)
    name = canonical[0] if len(canonical) == 1 else company.strip()
    return (name.lower(), fy.replace(" ", "").upper(), int(page))


def verify(answer: str, chunks: list[RetrievedChunk]) -> tuple[str, list[Citation], list[str]]:
    """Keep only citations that point at a retrieved chunk.

    Returns `(answer with invalid citations removed, valid citations in order, invalid strings)`.
    A bracket group may hold several citations separated by ';'.
    """
    by_key = {
        (c.chunk.company.lower(), c.chunk.fiscal_year.upper(), c.chunk.page): c for c in chunks
    }
    valid: dict[Key, Citation] = {}
    invalid: list[str] = []

    def rewrite(m: re.Match) -> str:
        parts = m.group(1).split(";")
        parsed = [_ONE.match(p) for p in parts]
        if not any(parsed):
            return m.group(0)  # not a citation (e.g. "[1]"), leave it alone
        kept = []
        for part, pm in zip(parts, parsed, strict=True):
            hit = by_key.get(_key(*pm.groups())) if pm else None
            if hit is None:
                invalid.append(part.strip())
                continue
            c = hit.chunk
            key = (c.company.lower(), c.fiscal_year.upper(), c.page)
            valid.setdefault(
                key,
                Citation(
                    company=c.company,
                    fiscal_year=c.fiscal_year,
                    page=c.page,
                    snippet=c.content[:300],
                    text=c.content,
                ),
            )
            kept.append(f"{c.company}, {c.fiscal_year}, p.{c.page}")
        return f"[{'; '.join(kept)}]" if kept else ""

    # gpt-oss often writes citations with full-width brackets: 【TCS, FY2026, p.211】
    answer = answer.translate(_BRACKET_VARIANTS)
    cleaned = _BRACKET.sub(rewrite, answer)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)  # tidy spaces left by removed tags
    return cleaned.strip(), list(valid.values()), invalid
