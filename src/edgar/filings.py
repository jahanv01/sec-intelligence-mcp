"""Fetch a company's recent filings (10-K / 10-Q) from the EDGAR submissions API."""

from pathlib import Path

import duckdb
import httpx
from pydantic import BaseModel

from config import SEC_EDGAR_USER_AGENT
from edgar.lookup import get_cik

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "edgar.duckdb"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filings (
    cik TEXT NOT NULL,
    ticker TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    accession_number TEXT PRIMARY KEY,
    primary_doc_url TEXT NOT NULL,
    fetched BOOLEAN DEFAULT FALSE
)
"""


class Filing(BaseModel):
    cik: str
    ticker: str
    form_type: str
    filing_date: str
    accession_number: str
    primary_doc_url: str


def _document_url(cik: str, accession_number: str, primary_document: str) -> str:
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        f"{accession_no_dashes}/{primary_document}"
    )


def get_recent_filings(ticker: str, form_type: str = "10-K", limit: int = 5) -> list[Filing]:
    ticker = ticker.upper()
    cik = get_cik(ticker)

    response = httpx.get(
        SUBMISSIONS_URL.format(cik=cik),
        headers={"User-Agent": SEC_EDGAR_USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    recent = response.json()["filings"]["recent"]

    filings: list[Filing] = []
    for i in range(len(recent["form"])):
        if recent["form"][i] != form_type:
            continue
        filings.append(
            Filing(
                cik=cik,
                ticker=ticker,
                form_type=recent["form"][i],
                filing_date=recent["filingDate"][i],
                accession_number=recent["accessionNumber"][i],
                primary_doc_url=_document_url(
                    cik, recent["accessionNumber"][i], recent["primaryDocument"][i]
                ),
            )
        )
        if len(filings) == limit:
            break

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        for f in filings:
            conn.execute(
                """
                INSERT INTO filings
                    (cik, ticker, form_type, filing_date, accession_number, primary_doc_url)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (accession_number) DO NOTHING
                """,
                [
                    f.cik,
                    f.ticker,
                    f.form_type,
                    f.filing_date,
                    f.accession_number,
                    f.primary_doc_url,
                ],
            )

    return filings
