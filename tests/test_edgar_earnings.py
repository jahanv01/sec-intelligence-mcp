"""Tests for edgar/earnings.py: locating and fetching 8-K earnings press releases."""

from types import SimpleNamespace

import pytest

from edgar import earnings

FAKE_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "8-K", "10-K", "8-K"],
            "items": ["2.02,9.01", "5.02", "", "2.02,9.01"],
            "filingDate": ["2024-05-02", "2024-03-01", "2024-04-15", "2024-01-25"],
            "reportDate": ["2024-05-02", "2024-03-01", "2024-04-15", "2024-01-25"],
            "accessionNumber": [
                "0000320193-24-000067",
                "0000320193-24-000040",
                "0000320193-24-000050",
                "0000320193-24-000010",
            ],
        }
    }
}

FAKE_INDEX_HTML = b"""
<html><body>
<table class="tableFile" summary="Document Format Files">
<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr class="oddRow">
  <td>1</td><td>8-K</td>
  <td><a href="/Archives/edgar/data/320193/000032019324000067/a8-k.htm">a8-k.htm</a></td>
  <td>8-K</td><td>5000</td>
</tr>
<tr class="evenRow">
  <td>2</td><td>EX-99.1</td>
  <td><a href="/Archives/edgar/data/320193/000032019324000067/a8-kex991.htm">a8-kex991.htm</a></td>
  <td>EX-99.1</td><td>173484</td>
</tr>
</table>
</body></html>
"""


@pytest.fixture(autouse=True)
def _mock_cik(monkeypatch):
    monkeypatch.setattr(earnings, "get_cik", lambda ticker: "0000320193")


def test_parse_quarter_accepts_standard_format():
    assert earnings._parse_quarter("Q2 2024") == (2, 2024)
    assert earnings._parse_quarter("q1 2023") == (1, 2023)


def test_parse_quarter_rejects_bad_format():
    with pytest.raises(ValueError):
        earnings._parse_quarter("second quarter 2024")


def test_calendar_quarter_buckets_by_month():
    assert earnings._calendar_quarter("2024-05-02") == (2, 2024)
    assert earnings._calendar_quarter("2024-01-25") == (1, 2024)
    assert earnings._calendar_quarter("2024-11-01") == (4, 2024)


def test_find_earnings_8k_matches_item_202_and_quarter(monkeypatch):
    monkeypatch.setattr(
        earnings.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            json=lambda: FAKE_SUBMISSIONS, raise_for_status=lambda: None
        ),
    )
    result = earnings.find_earnings_8k("AAPL", "Q2 2024")
    assert result["accession_number"] == "0000320193-24-000067"


def test_find_earnings_8k_skips_non_earnings_and_wrong_quarter(monkeypatch):
    monkeypatch.setattr(
        earnings.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            json=lambda: FAKE_SUBMISSIONS, raise_for_status=lambda: None
        ),
    )
    assert earnings.find_earnings_8k("AAPL", "Q4 2024") is None


def test_find_exhibit_url_locates_ex_99_1(monkeypatch):
    monkeypatch.setattr(
        earnings.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            content=FAKE_INDEX_HTML, raise_for_status=lambda: None
        ),
    )
    url = earnings._find_exhibit_url("0000320193", "0000320193-24-000067")
    assert url == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000067/a8-kex991.htm"


def test_fetch_earnings_release_raises_when_no_filing_found(monkeypatch):
    monkeypatch.setattr(earnings, "find_earnings_8k", lambda ticker, quarter: None)
    with pytest.raises(ValueError, match="No earnings 8-K"):
        earnings.fetch_earnings_release("AAPL", "Q4 2024")


def test_fetch_earnings_release_raises_when_no_exhibit_found(monkeypatch):
    monkeypatch.setattr(
        earnings,
        "find_earnings_8k",
        lambda ticker, quarter: {"cik": "0000320193", "accession_number": "0000320193-24-000067"},
    )
    monkeypatch.setattr(earnings, "_find_exhibit_url", lambda cik, accession: None)
    with pytest.raises(ValueError, match="no EX-99.1 exhibit"):
        earnings.fetch_earnings_release("AAPL", "Q2 2024")


def test_fetch_earnings_release_returns_extracted_text(monkeypatch):
    monkeypatch.setattr(
        earnings,
        "find_earnings_8k",
        lambda ticker, quarter: {"cik": "0000320193", "accession_number": "0000320193-24-000067"},
    )
    monkeypatch.setattr(
        earnings, "_find_exhibit_url", lambda cik, accession: "https://example.com/ex991.htm"
    )
    monkeypatch.setattr(
        earnings.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            content=b"<html><body><p>Revenue was $90.8 billion.</p></body></html>",
            raise_for_status=lambda: None,
        ),
    )
    text = earnings.fetch_earnings_release("AAPL", "Q2 2024")
    assert "Revenue was $90.8 billion." in text
