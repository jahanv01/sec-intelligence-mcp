"""Tests for tools/analyze_filing.py."""

import pytest

from retrieval.search import RetrievedChunk
from tools import analyze_filing as tool


def _fake_result(
    score: float, section: str = "Item 7", text: str = "Revenue grew."
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        section_name=section,
        page_number=42,
        score=score,
        accession_number="0001045810-25-000023",
        ticker="NVDA",
        fiscal_year=2025,
    )


async def test_no_results_returns_graceful_message_without_calling_llm(monkeypatch):
    monkeypatch.setattr(tool, "_search", lambda *a, **k: [])
    called = []
    monkeypatch.setattr(
        tool, "generate", lambda prompt: called.append(prompt) or "should not be called"
    )

    result = await tool.analyze_filing("what is the revenue?", "NVDA")

    assert not called
    assert "ingest_company_filings" in result["answer"]
    assert result["sources"] == []
    assert result["confidence"] == "low"


async def test_builds_prompt_with_question_and_context(monkeypatch):
    captured = {}

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return "the answer"

    monkeypatch.setattr(tool, "_search", lambda *a, **k: [_fake_result(0.85)])
    monkeypatch.setattr(tool, "generate", fake_generate)

    result = await tool.analyze_filing("what drove revenue growth?", "NVDA")

    assert "what drove revenue growth?" in captured["prompt"]
    assert "Revenue grew." in captured["prompt"]
    assert "Item 7" in captured["prompt"]
    assert result["answer"] == "the answer"


async def test_returns_sources_with_citation_fields(monkeypatch):
    monkeypatch.setattr(
        tool, "_search", lambda *a, **k: [_fake_result(0.85), _fake_result(0.75, "Item 1A")]
    )
    monkeypatch.setattr(tool, "generate", lambda prompt: "answer")

    result = await tool.analyze_filing("q", "NVDA")

    assert len(result["sources"]) == 2
    for source in result["sources"]:
        assert set(source.keys()) == {"section_name", "page_number", "text"}


@pytest.mark.parametrize(
    "score,expected",
    [(0.9, "high"), (0.8, "high"), (0.7, "medium"), (0.65, "medium"), (0.5, "low")],
)
async def test_confidence_thresholds(monkeypatch, score, expected):
    monkeypatch.setattr(tool, "_search", lambda *a, **k: [_fake_result(score)])
    monkeypatch.setattr(tool, "generate", lambda prompt: "answer")

    result = await tool.analyze_filing("q", "NVDA")
    assert result["confidence"] == expected
