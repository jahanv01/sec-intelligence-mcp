"""Tests for tools/get_earnings_summary.py."""

import json

from tools import get_earnings_summary as tool


async def test_returns_error_when_no_earnings_release_found(monkeypatch):
    def fake_fetch(ticker, quarter):
        raise ValueError(f"No earnings 8-K found for {ticker} {quarter}")

    monkeypatch.setattr(tool, "fetch_earnings_release", fake_fetch)

    result = await tool.get_earnings_summary("AAPL", "Q4 1999")

    assert "error" in result
    assert result["headline_metrics"] == []
    assert result["management_statements"] == []


async def test_parses_json_summary_from_llm(monkeypatch):
    monkeypatch.setattr(
        tool, "fetch_earnings_release", lambda ticker, quarter: "press release text"
    )
    monkeypatch.setattr(
        tool,
        "generate",
        lambda prompt: json.dumps(
            {
                "headline_metrics": ["Revenue $90.8B, down 4% YoY"],
                "management_statements": [
                    {"speaker": "Tim Cook", "statement": "Services set an all-time record."}
                ],
                "guidance": ["Expects growth to accelerate next quarter"],
                "tone_summary": "Confident despite revenue decline.",
            }
        ),
    )

    result = await tool.get_earnings_summary("AAPL", "Q2 2024")

    assert result["headline_metrics"] == ["Revenue $90.8B, down 4% YoY"]
    assert result["management_statements"][0]["speaker"] == "Tim Cook"
    assert result["tone_summary"] == "Confident despite revenue decline."


async def test_prompt_includes_ticker_quarter_and_text(monkeypatch):
    captured = {}

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return "{}"

    monkeypatch.setattr(tool, "fetch_earnings_release", lambda ticker, quarter: "raw press release")
    monkeypatch.setattr(tool, "generate", fake_generate)

    await tool.get_earnings_summary("AAPL", "Q2 2024")

    assert "AAPL" in captured["prompt"]
    assert "Q2 2024" in captured["prompt"]
    assert "raw press release" in captured["prompt"]


async def test_malformed_llm_output_falls_back_to_tone_summary(monkeypatch):
    monkeypatch.setattr(tool, "fetch_earnings_release", lambda ticker, quarter: "text")
    monkeypatch.setattr(tool, "generate", lambda prompt: "not valid json at all")

    result = await tool.get_earnings_summary("AAPL", "Q2 2024")

    assert result["headline_metrics"] == []
    assert result["tone_summary"] == "not valid json at all"


async def test_strips_markdown_json_fences(monkeypatch):
    monkeypatch.setattr(tool, "fetch_earnings_release", lambda ticker, quarter: "text")
    monkeypatch.setattr(
        tool,
        "generate",
        lambda prompt: '```json\n{"headline_metrics": ["x"]}\n```',
    )

    result = await tool.get_earnings_summary("AAPL", "Q2 2024")

    assert result["headline_metrics"] == ["x"]
