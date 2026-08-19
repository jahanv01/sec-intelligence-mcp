"""Locate and fetch SEC 8-K earnings press releases (the Exhibit 99.1 attachment)."""

import re

import httpx
from bs4 import BeautifulSoup

from config import SEC_EDGAR_USER_AGENT
from edgar.lookup import get_cik
from edgar.parser import extract_html_text

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EARNINGS_ITEM_CODE = "2.02"  # "Results of Operations and Financial Condition"

_QUARTER_RE = re.compile(r"^Q([1-4])\s*(\d{4})$", re.IGNORECASE)


def _parse_quarter(quarter: str) -> tuple[int, int]:
    match = _QUARTER_RE.match(quarter.strip())
    if not match:
        raise ValueError(f"Expected quarter format like 'Q2 2024', got {quarter!r}")
    return int(match.group(1)), int(match.group(2))


def _calendar_quarter(date_str: str) -> tuple[int, int]:
    year, month = int(date_str[:4]), int(date_str[5:7])
    return (month - 1) // 3 + 1, year


def find_earnings_8k(ticker: str, quarter: str) -> dict | None:
    """Finds the earnings 8-K (item 2.02) whose reportDate falls in the given calendar
    quarter -- e.g. quarter="Q2 2024" matches a filing reported in Apr-Jun 2024."""
    target = _parse_quarter(quarter)
    cik = get_cik(ticker.upper())

    response = httpx.get(
        SUBMISSIONS_URL.format(cik=cik), headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=30
    )
    response.raise_for_status()
    recent = response.json()["filings"]["recent"]

    for i in range(len(recent["form"])):
        if recent["form"][i] != "8-K" or EARNINGS_ITEM_CODE not in recent["items"][i]:
            continue
        report_date = recent["reportDate"][i] or recent["filingDate"][i]
        if _calendar_quarter(report_date) == target:
            return {
                "cik": cik,
                "accession_number": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "report_date": report_date,
            }
    return None


def _find_exhibit_url(cik: str, accession_number: str, exhibit_type: str = "EX-99.1") -> str | None:
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        f"{accession_no_dashes}/{accession_number}-index.htm"
    )
    response = httpx.get(index_url, headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not any(cell.get_text(strip=True) == exhibit_type for cell in cells):
            continue
        link = row.find("a", href=True)
        if link:
            href = link["href"]
            return f"https://www.sec.gov{href}" if href.startswith("/") else href
    return None


def fetch_earnings_release(ticker: str, quarter: str) -> str:
    """Fetches the text of a company's earnings press release (the EX-99.1 exhibit of its
    earnings 8-K) for the given calendar quarter, e.g. fetch_earnings_release("AAPL", "Q2 2024").

    Raises ValueError if no matching 8-K or EX-99.1 exhibit is found.
    """
    filing = find_earnings_8k(ticker, quarter)
    if filing is None:
        raise ValueError(f"No earnings 8-K found for {ticker.upper()} {quarter}")

    exhibit_url = _find_exhibit_url(filing["cik"], filing["accession_number"])
    if exhibit_url is None:
        raise ValueError(
            f"Found 8-K {filing['accession_number']} for {ticker.upper()} {quarter} but no "
            "EX-99.1 exhibit was listed in its index"
        )

    response = httpx.get(exhibit_url, headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=60)
    response.raise_for_status()
    return extract_html_text(response.content)
