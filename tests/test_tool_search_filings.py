"""Tests for tools/search_filings.py."""

from retrieval.search import RetrievedChunk
from tools import search_filings as tool


def _fake_result(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        text="Data center revenue grew significantly.",
        section_name="Item 7",
        page_number=None,
        score=score,
        accession_number="0001045810-25-000023",
        ticker="NVDA",
        fiscal_year=2025,
    )


async def test_reshapes_results_to_expected_dict_keys(monkeypatch):
    monkeypatch.setattr(tool, "_search", lambda *a, **k: [_fake_result(0.87)])

    results = await tool.search_filings("data center revenue", "NVDA")

    assert results == [
        {
            "text": "Data center revenue grew significantly.",
            "section": "Item 7",
            "page_number": None,
            "fiscal_year": 2025,
            "relevance_score": 0.87,
        }
    ]


async def test_top_k_clamped_to_valid_range(monkeypatch):
    captured = {}

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(tool, "_search", fake_search)
    await tool.search_filings("revenue", "NVDA", top_k=99)
    assert captured["top_k"] == 10

    await tool.search_filings("revenue", "NVDA", top_k=0)
    assert captured["top_k"] == 1


async def test_passes_through_filters(monkeypatch):
    captured = {}

    def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return []

    monkeypatch.setattr(tool, "_search", fake_search)
    await tool.search_filings("revenue", "NVDA", form_type="10-Q", fiscal_year=2024, top_k=3)

    assert captured["query"] == "revenue"
    assert captured["ticker"] == "NVDA"
    assert captured["form_type"] == "10-Q"
    assert captured["fiscal_year"] == 2024
    assert captured["top_k"] == 3
