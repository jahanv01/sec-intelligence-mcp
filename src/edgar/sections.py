"""Section detection and metadata extraction for 10-K filings.

10-Ks follow a standard Item 1 / Item 1A / ... structure, but the flattened, tag-stripped text
produced by parser.py also contains a Table of Contents that lists every item name near the top
as plain text. See detect_sections() for how TOC false positives are filtered out.
"""

import re
from pathlib import Path

import duckdb
from pydantic import BaseModel

from edgar.parser import ParsedFiling

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "edgar.duckdb"

CANONICAL_ITEMS = [
    "1", "1A", "1B", "1C", "2", "3", "4",
    "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
    "10", "11", "12", "13", "14", "15", "16",
]  # fmt: skip
_CANONICAL_ITEMS_SET = set(CANONICAL_ITEMS)

_ITEM_LINE_RE = re.compile(
    r"^[ \t]*ITEM[ \t]+(\d{1,2}[A-C]?)\b[.:\-–—]?",
    re.IGNORECASE | re.MULTILINE,
)

_COMPANY_NAME_RE = re.compile(
    r"([A-Z][A-Za-z0-9&.,'\-\s]{1,80}?)\s*\n\s*\(Exact [Nn]ame of [Rr]egistrant"
)
_FISCAL_YEAR_END_RE = re.compile(
    r"for the fiscal year ended\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE
)
_FISCAL_YEAR_END_RE_ALT = re.compile(
    r"for the year ended\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE
)
_AUDITOR_HEADING_RE = re.compile(
    r"Report of Independent Registered Public Accounting Firm", re.IGNORECASE
)
_KNOWN_AUDITORS_RE = re.compile(
    r"(Deloitte\s*&\s*Touche LLP|Ernst\s*&\s*Young LLP|KPMG LLP|"
    r"PricewaterhouseCoopers LLP|BDO USA,?\s*P\.?A\.?|Grant Thornton LLP|"
    r"RSM US LLP|Moss Adams LLP|Crowe LLP|Marcum LLP)",
    re.IGNORECASE,
)
_GENERIC_AUDITOR_RE = re.compile(r"\n\s*([A-Z][A-Za-z&,.\s]{2,60}?LLP)\s*\n")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filing_sections (
    accession_number TEXT NOT NULL,
    section_name TEXT NOT NULL,
    section_text TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    PRIMARY KEY (accession_number, section_name)
)
"""


class Section(BaseModel):
    section_name: str  # canonical form, e.g. "Item 1A", "Item 7"
    section_text: str
    char_start: int
    char_end: int


class FilingMetadata(BaseModel):
    company_name: str | None = None
    fiscal_year_end: str | None = None
    report_date: str | None = None
    auditor: str | None = None


def _filter_monotonic(last_occurrence: dict[str, int]) -> list[tuple[str, int]]:
    """Drop any item whose last occurrence sits before an earlier-numbered item's."""
    rank = {key: i for i, key in enumerate(CANONICAL_ITEMS)}
    by_canonical_order = sorted(last_occurrence.items(), key=lambda kv: rank[kv[0]])
    kept: list[tuple[str, int]] = []
    max_pos = -1
    for item_key, pos in by_canonical_order:
        if pos > max_pos:
            kept.append((item_key, pos))
            max_pos = pos
    return kept


def detect_sections(raw_text: str) -> list[Section]:
    """Find 10-K Item section boundaries in flattened filing text.

    A naive scan for "Item N" headers also matches the Table of Contents, which lists every
    item near the top of the document as plain text. Since the TOC structurally precedes the
    real document body, keeping only the LAST occurrence of each item key reliably skips it
    without needing a tuned length/gap threshold (which would misclassify genuinely short
    sections like Item 1B or Item 6 "[Reserved]" as TOC noise).
    """
    if not raw_text:
        return []

    last_occurrence: dict[str, int] = {}
    for m in _ITEM_LINE_RE.finditer(raw_text):
        item_key = m.group(1).upper()
        if item_key in _CANONICAL_ITEMS_SET:
            last_occurrence[item_key] = m.start()

    if not last_occurrence:
        return []

    ordered = _filter_monotonic(last_occurrence)
    ordered.sort(key=lambda kv: kv[1])

    sections: list[Section] = []
    for i, (item_key, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(raw_text)
        sections.append(
            Section(
                section_name=f"Item {item_key}",
                section_text=raw_text[start:end],
                char_start=start,
                char_end=end,
            )
        )
    return sections


def extract_metadata(raw_text: str) -> FilingMetadata:
    company_name = None
    if m := _COMPANY_NAME_RE.search(raw_text):
        company_name = m.group(1).strip()

    period_date = None
    if m := (_FISCAL_YEAR_END_RE.search(raw_text) or _FISCAL_YEAR_END_RE_ALT.search(raw_text)):
        period_date = m.group(1).strip()

    auditor = None
    headings = [m.start() for m in _AUDITOR_HEADING_RE.finditer(raw_text)]
    if headings:
        window = raw_text[headings[-1] : headings[-1] + 4000]
        m = _KNOWN_AUDITORS_RE.search(window) or _GENERIC_AUDITOR_RE.search(window)
        if m:
            auditor = m.group(1).strip()

    return FilingMetadata(
        company_name=company_name,
        fiscal_year_end=period_date,
        report_date=period_date,
        auditor=auditor,
    )


def store_sections(accession_number: str, sections: list[Section]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        for s in sections:
            conn.execute(
                """
                INSERT INTO filing_sections
                    (accession_number, section_name, section_text, char_start, char_end)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (accession_number, section_name) DO UPDATE SET
                    section_text = excluded.section_text,
                    char_start = excluded.char_start,
                    char_end = excluded.char_end
                """,
                [accession_number, s.section_name, s.section_text, s.char_start, s.char_end],
            )


def parse_and_store_sections(parsed: ParsedFiling) -> list[Section]:
    sections = detect_sections(parsed.raw_text)
    store_sections(parsed.accession_number, sections)
    return sections
