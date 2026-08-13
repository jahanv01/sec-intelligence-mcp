"""Tests for edgar/filings.py: filtering + storing recent filings from EDGAR submissions."""

from types import SimpleNamespace

import pytest

from edgar import filings

FAKE_SUBMISSIONS_RESPONSE = {
    "filings": {
        "recent": {
            "form": ["10-K", "8-K", "10-K", "10-Q", "10-K"],
            "filingDate": ["2025-10-31", "2025-08-01", "2024-10-25", "2025-01-15", "2023-10-27"],
            "accessionNumber": [
                "0000320193-25-000079",
                "0000320193-25-000050",
                "0000320193-24-000079",
                "0000320193-25-000010",
                "0000320193-23-000079",
            ],
            "primaryDocument": [
                "aapl-20250927.htm",
                "aapl-20250801.htm",
                "aapl-20240928.htm",
                "aapl-20241228.htm",
                "aapl-20230930.htm",
            ],
        }
    }
}


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(filings, "DB_PATH", tmp_path / "edgar.duckdb")


@pytest.fixture(autouse=True)
def _mock_dependencies(monkeypatch):
    monkeypatch.setattr(filings, "get_cik", lambda ticker: "0000320193")
    monkeypatch.setattr(
        filings.httpx,
        "get",
        lambda url, headers=None, timeout=None: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: FAKE_SUBMISSIONS_RESPONSE,
        ),
    )


def test_filters_by_form_type_and_respects_limit():
    result = filings.get_recent_filings("AAPL", "10-K", limit=2)
    assert len(result) == 2
    assert all(f.form_type == "10-K" for f in result)
    assert result[0].accession_number == "0000320193-25-000079"


def test_builds_correct_document_url():
    result = filings.get_recent_filings("AAPL", "10-K", limit=1)
    assert result[0].primary_doc_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
    )


def test_returns_valid_filing_objects():
    result = filings.get_recent_filings("AAPL", "10-K", limit=3)
    assert len(result) == 3
    for f in result:
        assert f.accession_number
        assert f.cik == "0000320193"
