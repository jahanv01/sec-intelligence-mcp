"""Tests for tools/get_filing_summary.py."""

from retrieval.search import RetrievedChunk
from tools import get_filing_summary as tool


def _fake_result(section: str) -> RetrievedChunk:
    return RetrievedChunk(
        text=f"Some {section} text.",
        section_name=section,
        page_number=None,
        score=0.8,
        accession_number="0001045810-25-000023",
        ticker="NVDA",
        fiscal_year=2025,
    )


def _mock_pipeline(monkeypatch):
    monkeypatch.setattr(tool, "get_company_name", lambda ticker: "NVIDIA CORP")
    monkeypatch.setattr(
        tool, "_search", lambda query, section_name=None, **k: [_fake_result(section_name)]
    )
    monkeypatch.setattr(tool, "generate", lambda prompt: "generated summary text")


async def test_no_ingested_filing_returns_error(monkeypatch):
    monkeypatch.setattr(tool, "_resolve_fiscal_year", lambda ticker, form_type: None)
    result = await tool.get_filing_summary("ZZZZ")
    assert "error" in result
    assert "ingest_company_filings" in result["error"]


async def test_returns_all_six_fields_non_empty(monkeypatch):
    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(tool, "_resolve_fiscal_year", lambda ticker, form_type: 2025)

    result = await tool.get_filing_summary("NVDA")

    expected_keys = {
        "company",
        "business_overview",
        "key_financials",
        "growth_discussion",
        "top_risks",
        "outlook",
    }
    assert set(result.keys()) == expected_keys
    for key, value in result.items():
        assert value, f"{key} should not be empty"
    assert "NVIDIA CORP" in result["company"]
    assert "2025" in result["company"]


async def test_explicit_fiscal_year_skips_resolution(monkeypatch):
    _mock_pipeline(monkeypatch)

    def fail_if_called(ticker, form_type):
        raise AssertionError("should not resolve fiscal year when explicitly given")

    monkeypatch.setattr(tool, "_resolve_fiscal_year", fail_if_called)

    result = await tool.get_filing_summary("NVDA", fiscal_year=2024)
    assert "2024" in result["company"]


async def test_each_field_queries_its_own_section(monkeypatch):
    monkeypatch.setattr(tool, "get_company_name", lambda ticker: "NVIDIA CORP")
    monkeypatch.setattr(tool, "_resolve_fiscal_year", lambda ticker, form_type: 2025)
    monkeypatch.setattr(tool, "generate", lambda prompt: "text")

    captured_sections = []

    def fake_search(query, section_name=None, **k):
        captured_sections.append(section_name)
        return [_fake_result(section_name)]

    monkeypatch.setattr(tool, "_search", fake_search)
    await tool.get_filing_summary("NVDA")

    assert captured_sections == ["Item 1", "Item 8", "Item 7", "Item 1A", "Item 7"]
