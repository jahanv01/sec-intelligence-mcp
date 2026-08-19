"""Tests for tools/detect_financial_anomalies.py."""

import json

from tools import detect_financial_anomalies as tool


def _mock_years(monkeypatch, years):
    monkeypatch.setattr(tool, "get_ingested_fiscal_years", lambda ticker, form_type: years)


def _mock_sections(monkeypatch, text_by_year):
    def fake_get_section(ticker, year, section, form_type):
        return text_by_year.get(year)

    monkeypatch.setattr(tool, "get_full_section_text", fake_get_section)


async def test_errors_when_fewer_than_two_years_available(monkeypatch):
    _mock_years(monkeypatch, [2025])
    result = await tool.detect_financial_anomalies("NVDA", years=3)
    assert result["anomalies"] == []
    assert "error" in result


async def test_compares_consecutive_year_pairs(monkeypatch):
    _mock_years(monkeypatch, [2025, 2024, 2023])  # most recent first, as the real helper returns
    _mock_sections(
        monkeypatch,
        {2023: "old text", 2024: "mid text", 2025: "new text"},
    )
    compared_pairs = []

    def fake_generate(prompt):
        # crude check: figure out which pair this prompt is for from the years embedded in it
        for a, b in [(2023, 2024), (2024, 2025)]:
            if f"FY{a}" in prompt and f"FY{b}" in prompt:
                compared_pairs.append((a, b))
        return "[]"

    monkeypatch.setattr(tool, "generate", fake_generate)

    result = await tool.detect_financial_anomalies("NVDA", years=3)

    assert result["years_analyzed"] == [2023, 2024, 2025]
    assert set(compared_pairs) == {(2023, 2024), (2024, 2025)}


async def test_parses_json_anomalies_and_tags_metadata(monkeypatch):
    _mock_years(monkeypatch, [2024, 2023])
    _mock_sections(monkeypatch, {2023: "old", 2024: "new"})
    monkeypatch.setattr(
        tool,
        "generate",
        lambda prompt: json.dumps(
            [{"description": "Data center revenue surged", "severity": "high"}]
        ),
    )

    result = await tool.detect_financial_anomalies("NVDA", years=2)

    assert len(result["anomalies"]) == 2  # one per section (Item 7 and Item 1A)
    item = result["anomalies"][0]
    assert item["description"] == "Data center revenue surged"
    assert item["severity"] == "high"
    assert item["years_compared"] == "FY2023 vs FY2024"
    assert item["section"] in ("Item 7", "Item 1A")


async def test_strips_markdown_json_fences(monkeypatch):
    _mock_years(monkeypatch, [2024, 2023])
    _mock_sections(monkeypatch, {2023: "old", 2024: "new"})
    monkeypatch.setattr(
        tool,
        "generate",
        lambda prompt: '```json\n[{"description": "x", "severity": "low"}]\n```',
    )

    result = await tool.detect_financial_anomalies("NVDA", years=2)

    assert result["anomalies"][0]["description"] == "x"


async def test_malformed_llm_output_falls_back_gracefully(monkeypatch):
    _mock_years(monkeypatch, [2024, 2023])
    _mock_sections(monkeypatch, {2023: "old", 2024: "new"})
    monkeypatch.setattr(tool, "generate", lambda prompt: "not valid json at all")

    result = await tool.detect_financial_anomalies("NVDA", years=2)

    assert len(result["anomalies"]) == 2
    assert result["anomalies"][0]["description"] == "not valid json at all"
    assert result["anomalies"][0]["severity"] == "medium"


async def test_skips_section_missing_for_either_year(monkeypatch):
    _mock_years(monkeypatch, [2024, 2023])
    _mock_sections(monkeypatch, {2024: "new text"})  # 2023 missing entirely
    monkeypatch.setattr(tool, "generate", lambda prompt: "[]")

    result = await tool.detect_financial_anomalies("NVDA", years=2)

    assert result["anomalies"] == []
