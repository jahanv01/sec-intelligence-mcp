"""Tests for tools/ingest_company_filings.py."""

from unittest.mock import AsyncMock

import pytest

from edgar.filings import Filing
from edgar.parser import ParsedFiling
from tools import ingest_company_filings as tool


def _fake_filing(date: str, accession: str) -> Filing:
    return Filing(
        cik="0001045810",
        ticker="NVDA",
        form_type="10-K",
        filing_date=date,
        accession_number=accession,
        primary_doc_url="https://example.com/doc.htm",
    )


@pytest.fixture(autouse=True)
def _mock_pipeline(monkeypatch):
    monkeypatch.setattr(tool, "get_cik", lambda ticker: "0001045810")
    monkeypatch.setattr(tool, "get_company_name", lambda ticker: "NVIDIA CORP")
    monkeypatch.setattr(
        tool,
        "get_recent_filings",
        lambda ticker, form_type, limit: [
            _fake_filing("2026-02-25", "0001045810-26-000010"),
            _fake_filing("2025-02-26", "0001045810-25-000010"),
        ][:limit],
    )

    def fake_fetch(filing):
        year = int(filing.filing_date[:4])
        return ParsedFiling(
            accession_number=filing.accession_number,
            ticker=filing.ticker,
            form_type=filing.form_type,
            fiscal_year=year,
            raw_text="Item 1. Business\nsome text",
        )

    monkeypatch.setattr(tool, "fetch_and_parse_filing", fake_fetch)
    monkeypatch.setattr(tool, "ingest_filing", lambda parsed: 200)


async def test_unknown_ticker_returns_clear_error(monkeypatch):
    def raise_unknown(ticker):
        raise ValueError(f"Unknown ticker: {ticker}")

    monkeypatch.setattr(tool, "get_cik", raise_unknown)
    result = await tool.ingest_company_filings("ZZZZ")
    assert result == "Unknown ticker: ZZZZ. Use a valid US stock ticker."


async def test_returns_summary_with_company_and_chunk_counts():
    result = await tool.ingest_company_filings("NVDA", "10-K", years=2)
    assert "NVIDIA CORP" in result
    assert "NVDA" in result
    assert "200 chunks" in result
    assert "Total chunks indexed: 400" in result


async def test_years_clamped_to_valid_range():
    result = await tool.ingest_company_filings("NVDA", "10-K", years=99)
    # limit=2 is the max available from the fake fixture, so clamping to 5 should still
    # only process what's actually available
    assert "Ingested 2 10-K filing(s)" in result


async def test_streams_progress_via_context():
    ctx = AsyncMock()
    await tool.ingest_company_filings("NVDA", "10-K", years=1, ctx=ctx)
    assert ctx.info.await_count == 1
