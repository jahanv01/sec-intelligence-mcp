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

# [ \t] alone misses real headings some filers render with a non-breaking space (HTML &nbsp;,
# \xa0 after tag-stripping) between "Item" and the number -- e.g. Amazon's actual "Item 1A"
# heading, and NVIDIA's actual "Item 8" heading. Without \xa0 here, those real headings are
# invisible to this regex and only each item's Table-of-Contents mention (which uses an
# ordinary space) gets matched.
_ITEM_LINE_RE = re.compile(
    r"^[ \t\xa0]*ITEM[ \t\xa0]+(\d{1,2}[A-C]?)\b[.:\-–—]?",
    re.IGNORECASE | re.MULTILINE,
)

# A 10-K's TOC lists every item in one dense run -- entries only tens to a couple hundred chars
# apart ("Item N. Title .... page"). The real document body follows a much larger gap (cover
# page boilerplate, forward-looking-statements language, signature pages, etc.) before the
# first real Item heading. Measured across every filer in this project's test corpus (AAPL,
# AMD, AMZN, GOOGL, MSFT, NVDA): TOC-internal gaps are consistently under 130 chars, and the
# gap out of the TOC is consistently 10,000+ chars -- 800 sits safely between the two with
# margin either side.
_TOC_GAP_THRESHOLD = 800

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


def _filter_monotonic(positions: dict[str, int]) -> list[tuple[str, int]]:
    """Drop any item whose position sits before an earlier-numbered item's."""
    rank = {key: i for i, key in enumerate(CANONICAL_ITEMS)}
    by_canonical_order = sorted(positions.items(), key=lambda kv: rank[kv[0]])
    kept: list[tuple[str, int]] = []
    max_pos = -1
    for item_key, pos in by_canonical_order:
        if pos > max_pos:
            kept.append((item_key, pos))
            max_pos = pos
    return kept


def _find_toc_boundary(matches: list[tuple[int, str]]) -> int:
    """Returns the char offset of the last match still inside the dense TOC run.

    Walks matches in document order and stops at the first gap larger than
    _TOC_GAP_THRESHOLD -- see that constant's docstring for why this reliably separates the
    TOC from the real body without a fixed TOC-length assumption.
    """
    boundary = matches[0][0]
    for i in range(1, len(matches)):
        if matches[i][0] - matches[i - 1][0] > _TOC_GAP_THRESHOLD:
            break
        boundary = matches[i][0]
    return boundary


def detect_sections(raw_text: str) -> list[Section]:
    """Find 10-K Item section boundaries in flattened filing text.

    A naive scan for "Item N" headers also matches the Table of Contents, which lists every
    item near the top of the document as plain text -- and, on some filers (seen on Microsoft's
    10-K), a running header/footer repeating "Item N" on every printed page throughout that
    item's entire real section. Neither "first occurrence" nor "last occurrence" alone survives
    both: first occurrence hits the TOC, last occurrence on a running-header filer lands near
    the *end* of the real section instead of its start. Instead, this locates where the TOC's
    dense run of entries ends (_find_toc_boundary) and takes the first occurrence of each item
    strictly after that point, falling back to the item's last occurrence anywhere in the
    document if it never reappears post-TOC (e.g. an item whose only real mention happens to
    be malformed) so a section is never dropped outright.
    """
    if not raw_text:
        return []

    matches = [
        (m.start(), m.group(1).upper())
        for m in _ITEM_LINE_RE.finditer(raw_text)
        if m.group(1).upper() in _CANONICAL_ITEMS_SET
    ]
    if not matches:
        return []

    toc_boundary = _find_toc_boundary(matches)

    last_overall: dict[str, int] = {}
    first_after_toc: dict[str, int] = {}
    for pos, item_key in matches:
        last_overall[item_key] = pos
        if pos > toc_boundary and item_key not in first_after_toc:
            first_after_toc[item_key] = pos

    positions = {**last_overall, **first_after_toc}

    ordered = _filter_monotonic(positions)
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
