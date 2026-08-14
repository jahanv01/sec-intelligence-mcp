"""Download and parse SEC filing documents (HTML or PDF) into clean text."""

import io
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from config import SEC_EDGAR_USER_AGENT
from edgar.filings import Filing

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "edgar.duckdb"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filing_content (
    accession_number TEXT PRIMARY KEY,
    raw_text TEXT NOT NULL,
    page_count INTEGER,
    fetched_at TIMESTAMP NOT NULL
)
"""


class ParsedFiling(BaseModel):
    accession_number: str
    ticker: str = ""
    form_type: str = ""
    fiscal_year: int | None = None
    raw_text: str
    page_count: int | None = None


def _extract_html_text(content: bytes) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text(separator="\n").splitlines())
    return "\n".join(line for line in lines if line)


def _extract_pdf_text(content: bytes) -> tuple[str, int]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages), len(pages)


def fetch_and_parse_filing(filing: Filing) -> ParsedFiling:
    response = httpx.get(
        filing.primary_doc_url, headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=60
    )
    response.raise_for_status()

    if filing.primary_doc_url.lower().endswith(".pdf"):
        raw_text, page_count = _extract_pdf_text(response.content)
    else:
        raw_text, page_count = _extract_html_text(response.content), None

    parsed = ParsedFiling(
        accession_number=filing.accession_number,
        ticker=filing.ticker,
        form_type=filing.form_type,
        fiscal_year=int(filing.filing_date[:4]),
        raw_text=raw_text,
        page_count=page_count,
    )

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.execute(
            """
            INSERT INTO filing_content (accession_number, raw_text, page_count, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (accession_number) DO UPDATE SET
                raw_text = excluded.raw_text,
                page_count = excluded.page_count,
                fetched_at = excluded.fetched_at
            """,
            [parsed.accession_number, parsed.raw_text, parsed.page_count, datetime.now(UTC)],
        )

    return parsed
