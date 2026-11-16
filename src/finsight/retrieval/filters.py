"""Deterministic extraction of company names and fiscal years from a question."""

import re

from pydantic import BaseModel

# canonical name (as stored in the DB) -> aliases, matched case-insensitively on word boundaries
COMPANY_ALIASES: dict[str, list[str]] = {
    "TCS": ["TCS", "Tata Consultancy Services", "Tata Consultancy"],
    "Infosys": ["Infosys", "Infy"],
    "Wipro": ["Wipro"],
    "HCLTech": ["HCLTech", "HCL Tech", "HCL Technologies", "HCL"],
    "Tech Mahindra": ["Tech Mahindra", "TechMahindra", "TechM", "Tech M"],
}
_COMPANY_PATTERNS = {
    name: re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.IGNORECASE)
    for name, aliases in COMPANY_ALIASES.items()
}

# FY26, FY2026, FY 2026, FY'26, F.Y. 2026
_FY = re.compile(r"\bF\.?Y\.?\s?'?(\d{4}|\d{2})\b", re.IGNORECASE)
# 2025-26, 2025–26, 2025/26, 2025-2026 (Indian financial year → named by its end year)
_RANGE = re.compile(r"\b(20\d{2})\s?[-–/]\s?(\d{4}|\d{2})\b")
# fiscal 2026, fiscal year 2026, financial year 2026
_FISCAL = re.compile(
    r"\b(?:fiscal|financial)(?:\s+year)?\s+(20\d{2})\b(?!\s?[-–/]\s?\d)",  # ranges handled above
    re.IGNORECASE,
)


class Filters(BaseModel):
    """Metadata filters for retrieval; an empty list means 'no filter'."""

    companies: list[str] = []
    fiscal_years: list[str] = []


def extract_companies(text: str) -> list[str]:
    """Canonical company names mentioned in `text`, in a stable order."""
    return [name for name, rx in _COMPANY_PATTERNS.items() if rx.search(text)]


def _full_year(y: str) -> int:
    return int(y) if len(y) == 4 else 2000 + int(y)


def extract_fiscal_years(text: str) -> list[str]:
    """Fiscal years mentioned in `text`, normalised to 'FY2026' form."""
    years = {_full_year(m.group(1)) for m in _FY.finditer(text)}
    for m in _RANGE.finditer(text):
        start, end = int(m.group(1)), _full_year(m.group(2))
        if end == start + 1:  # a financial-year range, not e.g. "2020-2030"
            years.add(end)
    years |= {int(m.group(1)) for m in _FISCAL.finditer(text)}
    return [f"FY{y}" for y in sorted(years)]


def extract_filters(text: str) -> Filters:
    """Company and fiscal-year filters found in a question."""
    return Filters(companies=extract_companies(text), fiscal_years=extract_fiscal_years(text))
