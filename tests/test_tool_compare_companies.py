"""Tests for tools/compare_companies.py."""

from retrieval.search import RetrievedChunk
from tools import compare_companies as tool


def _fake_result(ticker: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"fake-{ticker}",
        text=text,
        section_name="Item 7",
        page_number=None,
        score=0.85,
        accession_number=f"acc-{ticker}",
        ticker=ticker,
        fiscal_year=2025,
    )


def _mock_pipeline(monkeypatch, per_ticker_text=None):
    per_ticker_text = per_ticker_text or {}
    monkeypatch.setattr(tool, "get_most_recent_ingested_fiscal_year", lambda t, ft: 2025)
    monkeypatch.setattr(
        tool,
        "_search",
        lambda aspect, ticker, form_type, fiscal_year, top_k: [
            _fake_result(ticker, per_ticker_text.get(ticker, f"{ticker} says something."))
        ],
    )
    monkeypatch.setattr(tool, "generate", lambda prompt: "generated comparison")


async def test_requires_at_least_two_tickers(monkeypatch):
    result = await tool.compare_companies(["NVDA"], "AI strategy")
    assert "at least" in result["comparison"].lower()
    assert result["sources"] == {}


async def test_caps_at_four_tickers(monkeypatch):
    captured = {}
    _mock_pipeline(monkeypatch)

    def fake_search(aspect, ticker, form_type, fiscal_year, top_k):
        captured.setdefault("tickers", []).append(ticker)
        return [_fake_result(ticker, "text")]

    monkeypatch.setattr(tool, "_search", fake_search)

    await tool.compare_companies(["A", "B", "C", "D", "E"], "aspect")

    assert captured["tickers"] == ["A", "B", "C", "D"]


async def test_returns_comparison_and_per_company_sources(monkeypatch):
    _mock_pipeline(monkeypatch, {"NVDA": "NVDA leads in GPUs.", "AMD": "AMD competes closely."})

    result = await tool.compare_companies(["NVDA", "AMD"], "AI chip market position")

    assert result["comparison"] == "generated comparison"
    assert set(result["sources"].keys()) == {"NVDA", "AMD"}
    assert result["sources"]["NVDA"][0]["text"] == "NVDA leads in GPUs."
    assert result["sources"]["AMD"][0]["text"] == "AMD competes closely."


async def test_no_data_for_any_company_skips_llm_call(monkeypatch):
    called = []
    monkeypatch.setattr(tool, "get_most_recent_ingested_fiscal_year", lambda t, ft: None)
    monkeypatch.setattr(tool, "_search", lambda *a, **k: [])
    monkeypatch.setattr(tool, "generate", lambda prompt: called.append(1) or "should not be called")

    result = await tool.compare_companies(["ZZZZ", "YYYY"], "aspect")

    assert not called
    assert "ingest_company_filings" in result["comparison"]


async def test_prompt_includes_ticker_labeled_citations(monkeypatch):
    captured = {}

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return "comparison"

    _mock_pipeline(monkeypatch, {"NVDA": "NVDA text here.", "AMD": "AMD text here."})
    monkeypatch.setattr(tool, "generate", fake_generate)

    await tool.compare_companies(["NVDA", "AMD"], "AI chip market position")

    assert "[NVDA, Section: Item 7]" in captured["prompt"]
    assert "[AMD, Section: Item 7]" in captured["prompt"]
