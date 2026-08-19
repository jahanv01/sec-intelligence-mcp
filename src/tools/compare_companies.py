"""MCP tool: compare 2-4 companies on a specific aspect using their SEC filings."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio

from llm import generate
from retrieval.hybrid import hybrid_search as _search
from retrieval.ingest import get_most_recent_ingested_fiscal_year

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "compare_companies.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

TOP_K_PER_COMPANY = 5
MIN_TICKERS = 2
MAX_TICKERS = 4


def _retrieve_for_ticker(
    aspect: str, ticker: str, form_type: str, fiscal_year: int | None
) -> tuple[str, list]:
    year = fiscal_year or get_most_recent_ingested_fiscal_year(ticker, form_type)
    results = _search(
        aspect, ticker=ticker, form_type=form_type, fiscal_year=year, top_k=TOP_K_PER_COMPANY
    )
    return ticker, results


def _format_company_block(ticker: str, results: list) -> str:
    if not results:
        return f"=== {ticker} ===\n(No indexed filing content found for {ticker}.)"
    lines = [f"=== {ticker} ==="]
    for r in results:
        page = f", Page: {r.page_number}" if r.page_number else ""
        lines.append(f"[{ticker}, Section: {r.section_name}{page}]\n{r.text}")
    return "\n\n".join(lines)


def _compare_companies_sync(
    tickers: list[str], aspect: str, form_type: str, fiscal_year: int | None
) -> dict:
    tickers = [t.upper() for t in tickers]

    with ThreadPoolExecutor(max_workers=len(tickers)) as pool:
        futures = [
            pool.submit(_retrieve_for_ticker, aspect, t, form_type, fiscal_year) for t in tickers
        ]
        per_company = dict(f.result() for f in futures)

    if all(not results for results in per_company.values()):
        return {
            "comparison": (
                f"No indexed filing content found for any of {', '.join(tickers)}. "
                "Call ingest_company_filings first."
            ),
            "sources": {t: [] for t in tickers},
        }

    context = "\n\n".join(_format_company_block(t, per_company[t]) for t in tickers)
    prompt = _PROMPT_TEMPLATE.format(aspect=aspect, tickers=", ".join(tickers), context=context)
    comparison = generate(prompt)

    return {
        "comparison": comparison,
        "sources": {
            t: [
                {"section_name": r.section_name, "page_number": r.page_number, "text": r.text}
                for r in per_company[t]
            ]
            for t, results in per_company.items()
        },
    }


async def compare_companies(
    tickers: list[str],
    aspect: str,
    fiscal_year: int | None = None,
    form_type: str = "10-K",
) -> dict:
    """Compare two or more companies on a specific aspect using their SEC filings.

    All comparisons are grounded in the actual filing text with citations.

    Args:
        tickers: List of 2-4 ticker symbols
        aspect: What to compare -- e.g. 'R&D investment strategy', 'risk factors',
            'revenue growth discussion'
        fiscal_year: Year to compare (uses most recent for each company if omitted)
        form_type: '10-K' or '10-Q'

    Returns:
        comparison: Side-by-side analysis with citations for each company
        sources: Filing citations for each company's data points
    """
    tickers = tickers[:MAX_TICKERS]
    if len(tickers) < MIN_TICKERS:
        return {
            "comparison": f"compare_companies needs at least {MIN_TICKERS} tickers.",
            "sources": {},
        }

    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(
        _compare_companies_sync, tickers, aspect, form_type, fiscal_year
    )
