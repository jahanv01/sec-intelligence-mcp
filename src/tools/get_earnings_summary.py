"""MCP tool: summarize a company's earnings press release for a given quarter."""

import json
from pathlib import Path

import anyio

from edgar.earnings import fetch_earnings_release
from llm import generate, strip_json_fences

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "get_earnings_summary.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

_EMPTY_SUMMARY = {
    "headline_metrics": [],
    "management_statements": [],
    "guidance": [],
    "tone_summary": "",
}


def _get_earnings_summary_sync(ticker: str, quarter: str) -> dict:
    ticker = ticker.upper()

    try:
        text = fetch_earnings_release(ticker, quarter)
    except ValueError as e:
        return {**_EMPTY_SUMMARY, "error": str(e)}

    prompt = _PROMPT_TEMPLATE.format(ticker=ticker, quarter=quarter, text=text)
    raw = generate(prompt)

    try:
        summary = json.loads(strip_json_fences(raw))
        if not isinstance(summary, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, ValueError):
        # LLM didn't return clean JSON -- surface its raw text via tone_summary rather than
        # silently dropping the result.
        return {**_EMPTY_SUMMARY, "tone_summary": raw.strip()}

    return {**_EMPTY_SUMMARY, **summary}


async def get_earnings_summary(ticker: str, quarter: str) -> dict:
    """Summarize a company's earnings press release for a given quarter.

    Fetches the Exhibit 99.1 press release attached to the company's earnings 8-K filing
    and extracts headline metrics, management commentary, guidance, and overall tone.

    Args:
        ticker: Company ticker
        quarter: Calendar quarter to summarize, e.g. 'Q2 2024' (matches the quarter the
            earnings were reported in, not necessarily the company's own fiscal quarter label)

    Returns:
        headline_metrics: Key reported figures (revenue, EPS, margin, etc.)
        management_statements: Statements attributed to named executives, each with a
            speaker and statement
        guidance: Forward-looking statements about future quarters
        tone_summary: Brief description of the overall tone
        error: Present only if no matching earnings release could be found
    """
    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(_get_earnings_summary_sync, ticker, quarter)
