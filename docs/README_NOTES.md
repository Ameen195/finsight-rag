# Notes to carry into README (Limitations / Data)

- **Page numbers are physical PDF pages** (1-based, as a PDF viewer shows them), not the numbers
  printed on the page. For TCS the printed number is physical + 30 (e.g. physical p.211 is printed
  "241"); other reports have their own offsets.
- **TCS is parsed with full-page OCR** (RapidOCR via Docling) because its PDF text layer is broken:
  letters split or lost ("W ater", "ear ended"), digits spaced or dropped ("2, 67 022", a lost digit
  in "8,78,270"), and ₹ extracted as "H". The other four reports use the PDF text layer directly.
- **OCR limitations** (seen on TCS test pages):
  - "-" (nil) cells in tables come out blank.
  - The ₹ sign is sometimes lost in unit labels ("( crore)"), and unit labels can end up detached
    from their table.
  - Subscripts become noise (e.g. "tCO_{2e" for tCO₂e); occasional letter confusions such as "OCl"
    for "OCI".
- **Picture text is recovered selectively**: pages where Docling holds clearly fewer digits than
  the PDF text layer are re-parsed with text inside pictures (KPI tiles, infographics, charts).
  This brings back real figures (e.g. Infosys "₹666 cr global CSR", the FY2026 dividend box) but
  also **chart-axis noise** — bare number runs such as "0 2,000 4,000 … 18,000", year axes, and
  unlabelled series. Left in for now; its effect on retrieval is judged in the Phase 3 eval.
  Some infographics come out twice (as text and as a small table, e.g. Infosys p.37).
- **Digit cross-check limitation**: it skips a table cell equal to its left neighbour (to avoid
  counting merged spans twice), so tables with genuinely equal adjacent values (e.g. "100 | 100"
  holdings) show false "missing digits".
- **Infosys ₹ sign** is extracted as a backtick; a per-report `glyph_map` restores it at chunk time.
- **Sections come from PDF bookmarks** where they exist. Infosys has real section bookmarks;
  HCLTech and Tech Mahindra only have coarse, file-name-like bookmarks; TCS and Wipro have none, so
  their chunks carry no section label.
