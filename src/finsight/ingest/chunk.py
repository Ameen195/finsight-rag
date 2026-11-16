"""Chunking: ~400 bge-token text windows with overlap; tables standalone with their title.

Tokens are counted with the embedding model's own tokenizer, so a chunk plus its contextual
header fits bge-small's 512-token window instead of being silently truncated.
"""

import re
from functools import lru_cache

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from finsight.config import get_settings
from finsight.models import Chunk

TARGET_TOKENS = 400
OVERLAP_TOKENS = 50
MIN_TOKENS = 10
TINY_TABLE_TOKENS = 50
MAX_TITLE_TOKENS = 60
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")

# (word, page, separator before it, section)
Word = tuple[str, int, str, str | None]


@lru_cache(maxsize=1)
def _tokenizer() -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(get_settings().embedding_model)


def n_tokens(text: str) -> int:
    """bge-small token count, without [CLS]/[SEP]."""
    return len(_tokenizer()(text, add_special_tokens=False, verbose=False)["input_ids"])


def token_counts(texts: list[str]) -> list[int]:
    """Batched `n_tokens` (one tokenizer call for many strings)."""
    if not texts:
        return []
    ids = _tokenizer()(texts, add_special_tokens=False, verbose=False)["input_ids"]
    return [len(i) for i in ids]


def compact_table(md: str) -> str:
    """Strip Docling's cell padding and shorten `|-----|` rules.

    WordPiece makes one token per '-', so a padded separator row alone can cost 100+ tokens.
    Cell text is left untouched.
    """
    out = []
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and all(_SEPARATOR_CELL.match(c) for c in cells):
            cells = ["---"] * len(cells)
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def split_table(md: str, title: str = "", max_tokens: int = TARGET_TOKENS) -> list[str]:
    """Split a Markdown table by rows; each part = title + header + separator + some rows.

    A trailing part under TINY_TABLE_TOKENS is merged into the previous one.
    """
    lines = md.splitlines()
    head = ([title] if title else []) + lines[:2]
    whole = "\n".join(([title] if title else []) + lines)
    if len(lines) <= 3 or n_tokens(whole) <= max_tokens:
        return [whole]
    rows = lines[2:]
    budget = max_tokens - n_tokens("\n".join(head))
    parts: list[list[str]] = []
    cur: list[str] = []
    cur_tokens = 0
    for row, cost in zip(rows, token_counts(rows), strict=True):
        if cur and cur_tokens + cost > budget:
            parts.append(cur)
            cur, cur_tokens = [], 0
        cur.append(row)
        cur_tokens += cost
    if len(parts) >= 1 and cur_tokens < TINY_TABLE_TOKENS:
        parts[-1] += cur  # avoid a tiny last fragment; slightly over budget is fine
    else:
        parts.append(cur)
    return ["\n".join(head + p) for p in parts]


def _windows(words: list[Word]) -> list[tuple[str, int, str | None]]:
    """Pack words into ~TARGET_TOKENS windows; each next window re-starts ~OVERLAP_TOKENS back.

    Words (not raw tokens) are the unit so a window never ends mid-word.
    Each window keeps the page and section of its first word.
    """
    costs = token_counts([w for w, _, _, _ in words])
    remaining = [0] * (len(costs) + 1)  # remaining[i] = tokens from word i to the end
    for i in range(len(costs) - 1, -1, -1):
        remaining[i] = remaining[i + 1] + costs[i]
    out: list[tuple[str, int, str | None]] = []
    start = 0
    while start < len(words):
        end, total = start, 0
        while end < len(words) and (end == start or total + costs[end] <= TARGET_TOKENS):
            total += costs[end]
            end += 1
        if remaining[end] < TINY_TABLE_TOKENS:
            end = len(words)  # absorb a tiny tail instead of making a near-duplicate window
        text = words[start][0] + "".join(sep + w for w, _, sep, _ in words[start + 1 : end])
        out.append((text, words[start][1], words[start][3]))
        if end >= len(words):
            break
        back, overlap = end, 0
        while back > start + 1 and overlap + costs[back - 1] <= OVERLAP_TOKENS:
            back -= 1
            overlap += costs[back]
        start = back
    return out


def _table_title(table: dict, prev: dict | None) -> str:
    """Docling caption if any, else a short heading/text just before the table on its page."""
    if table.get("caption"):
        return table["caption"]
    if (
        prev
        and prev["type"] in ("heading", "text")
        and prev["page"] == table["page"]
        and any(ch.isalpha() for ch in prev["text"])  # skip stray "-" / "(1)" lines
        and n_tokens(prev["text"]) <= MAX_TITLE_TOKENS
    ):
        return prev["text"]
    return ""


def chunk_elements(
    elements: list[dict],
    company: str,
    fiscal_year: str,
    page_sections: dict[int, list[str]] | None = None,
) -> tuple[list[Chunk], int]:
    """Turn parsed elements into chunks. Returns `(chunks, dropped_count)`.

    Every chunk lies on exactly one page. `page_sections` maps page → bookmark path (section is
    None without bookmarks). Tables under TINY_TABLE_TOKENS are folded into the same page's text.
    Chunks under MIN_TOKENS are dropped unless they contain a digit.
    """
    page_sections = page_sections or {}
    candidates: list[tuple[str, int, str | None, bool]] = []
    words: list[Word] = []
    page: int | None = None
    prev: dict | None = None

    def flush() -> None:
        candidates.extend((t, p, s, False) for t, p, s in _windows(words))
        words.clear()

    def add_words(text: str, page: int, section: str | None) -> None:
        for i, w in enumerate(text.split()):
            words.append((w, page, "\n\n" if i == 0 else " ", section))

    for el in elements:
        section = " > ".join(page_sections.get(el["page"], [])) or None
        if el["page"] != page:  # a chunk never spans a page break → its citation page is exact
            flush()
            page = el["page"]
        if el["type"] == "table":
            md = compact_table(el["text"])
            if n_tokens(md) < TINY_TABLE_TOKENS:
                add_words(md, el["page"], section)
            else:
                title = _table_title(el, prev)
                candidates.extend((p, el["page"], section, True) for p in split_table(md, title))
        else:
            add_words(el["text"], el["page"], section)
        prev = el
    flush()

    chunks = [
        Chunk(company=company, fiscal_year=fiscal_year, page=p, section=s, content=t, is_table=tbl)
        for (t, p, s, tbl), n in zip(
            candidates, token_counts([c[0] for c in candidates]), strict=True
        )
        if n >= MIN_TOKENS or any(ch.isdigit() for ch in t)  # short figures are still answers
    ]
    return chunks, len(candidates) - len(chunks)


def embedding_text(chunk: Chunk) -> str:
    """Text actually embedded: a contextual header + the clean content."""
    return f"{chunk.company} | {chunk.fiscal_year} | {chunk.section or ''}\n{chunk.content}"
