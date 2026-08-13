"""Ticker -> CIK lookup, backed by a local DuckDB cache of SEC's ticker mapping."""

import json
import tempfile
from pathlib import Path

import duckdb
import httpx

from config import SEC_EDGAR_USER_AGENT

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "edgar.duckdb"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ticker_cik (
    ticker TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    company_name TEXT NOT NULL
)
"""


def _populate_if_empty(conn: duckdb.DuckDBPyConnection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM ticker_cik").fetchone()[0]
    if count > 0:
        return

    response = httpx.get(TICKERS_URL, headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=30)
    response.raise_for_status()
    rows = list(response.json().values())

    # DuckDB's native JSON reader loads ~10k rows in well under a second; binding
    # them one by one through the Python API (executemany, or even a single bulk
    # INSERT with list parameters) took 100+ seconds in testing on this machine.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(rows, tmp)
        tmp_path = Path(tmp.name)
    try:
        conn.execute(
            f"""
            INSERT INTO ticker_cik
            SELECT upper(ticker) AS ticker, printf('%010d', cik_str) AS cik, title AS company_name
            FROM read_json_auto('{tmp_path.as_posix()}')
            """
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def _lookup(ticker: str, column: str) -> str:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        _populate_if_empty(conn)
        result = conn.execute(
            f"SELECT {column} FROM ticker_cik WHERE ticker = ?", [ticker.upper()]
        ).fetchone()
    if result is None:
        raise ValueError(f"Unknown ticker: {ticker}")
    return result[0]


def get_cik(ticker: str) -> str:
    """Returns the zero-padded 10-digit CIK for a ticker, e.g. get_cik("NVDA") -> "0001045810"."""
    return _lookup(ticker, "cik")


def get_company_name(ticker: str) -> str:
    return _lookup(ticker, "company_name")
