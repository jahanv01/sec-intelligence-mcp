"""MCP tool: identify unusual year-over-year changes in a company's financial disclosures."""

import json
from pathlib import Path

import anyio

from llm import generate
from retrieval.ingest import get_full_section_text, get_ingested_fiscal_years

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "detect_anomalies.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

# MD&A (financial performance narrative) and Risk Factors (where new risks first appear).
SECTIONS_TO_COMPARE = ["Item 7", "Item 1A"]


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _compare_year_pair(ticker: str, form_type: str, year_a: int, year_b: int) -> list[dict]:
    anomalies = []
    for section in SECTIONS_TO_COMPARE:
        text_a = get_full_section_text(ticker, year_a, section, form_type)
        text_b = get_full_section_text(ticker, year_b, section, form_type)
        if not text_a or not text_b:
            continue

        prompt = _PROMPT_TEMPLATE.format(
            ticker=ticker,
            section=section,
            year_a=year_a,
            year_b=year_b,
            text_a=text_a,
            text_b=text_b,
        )
        raw = generate(prompt)

        try:
            parsed = json.loads(_strip_json_fences(raw))
            if not isinstance(parsed, list):
                raise ValueError("expected a JSON array")
        except (json.JSONDecodeError, ValueError):
            # LLM didn't return clean JSON -- surface its raw text as a single medium-severity
            # item rather than silently dropping the comparison.
            parsed = [{"description": raw.strip(), "severity": "medium"}]

        for item in parsed:
            item.setdefault("severity", "medium")
            item["section"] = section
            item["years_compared"] = f"FY{year_a} vs FY{year_b}"
            anomalies.append(item)

    return anomalies


def _detect_financial_anomalies_sync(ticker: str, years: int, form_type: str) -> dict:
    ticker = ticker.upper()
    available_years = get_ingested_fiscal_years(ticker, form_type)  # most recent first
    selected = sorted(available_years[:years])  # oldest -> newest, capped to `years`

    if len(selected) < 2:
        return {
            "anomalies": [],
            "error": (
                f"Need at least 2 ingested {form_type} filings for {ticker} to compare "
                f"year-over-year; found {len(selected)}. Call ingest_company_filings with a "
                "higher `years` value first."
            ),
        }

    anomalies = []
    for year_a, year_b in zip(selected, selected[1:], strict=False):
        anomalies.extend(_compare_year_pair(ticker, form_type, year_a, year_b))

    return {"anomalies": anomalies, "years_analyzed": selected}


async def detect_financial_anomalies(ticker: str, years: int = 3, form_type: str = "10-K") -> dict:
    """Identify unusual year-over-year changes in a company's financial disclosures.

    Compares management's language and reported metrics across multiple annual filings.

    Args:
        ticker: Company ticker
        years: Number of most recent ingested fiscal years to compare (default 3)
        form_type: '10-K' or '10-Q'

    Returns:
        anomalies: List of notable changes, each with a description, severity
            (high/medium/low), the section it came from, and which two fiscal years were
            compared
        years_analyzed: The fiscal years actually used for the comparison
    """
    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(
        _detect_financial_anomalies_sync, ticker, years, form_type
    )
