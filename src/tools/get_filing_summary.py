"""MCP tool: structured executive summary of a complete filing."""

from pathlib import Path

import anyio

from edgar.lookup import get_company_name
from llm import generate
from retrieval.ingest import get_most_recent_ingested_fiscal_year
from retrieval.search import search as _search

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "filing_summary.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

# field_name -> (section to pull from, retrieval query, how many chunks, extraction instruction)
_FIELDS: dict[str, tuple[str, str, int, str]] = {
    "business_overview": (
        "Item 1",
        "what does the company do, business overview",
        3,
        "describe what the company does in 2-3 concise sentences",
    ),
    "key_financials": (
        "Item 8",
        "revenue net income key financial metrics",
        5,
        "list the key financial metrics mentioned (such as revenue and net income) as short "
        "bullet points",
    ),
    "growth_discussion": (
        "Item 7",
        "revenue growth performance discussion drivers",
        5,
        "summarize management's discussion of the company's growth and financial performance "
        "in 2-3 concise sentences",
    ),
    "top_risks": (
        "Item 1A",
        "risk factors",
        8,
        "list the top 5 risk factors as short bullet points, one sentence each",
    ),
    "outlook": (
        "Item 7",
        "outlook guidance forward-looking statements future expectations",
        3,
        "summarize any forward-looking guidance or outlook mentioned in 1-2 sentences; if none "
        "is present in the excerpts, say 'No specific forward guidance provided.'",
    ),
}


def _resolve_fiscal_year(ticker: str, form_type: str) -> int | None:
    return get_most_recent_ingested_fiscal_year(ticker, form_type)


def _extract_field(
    ticker: str,
    form_type: str,
    fiscal_year: int,
    section_name: str,
    query: str,
    top_k: int,
    instruction: str,
) -> str:
    results = _search(
        query,
        ticker=ticker,
        form_type=form_type,
        fiscal_year=fiscal_year,
        section_name=section_name,
        top_k=top_k,
    )
    if not results:
        return "Not available in the indexed filing."
    context = "\n\n".join(r.text for r in results)
    prompt = _PROMPT_TEMPLATE.format(task_instruction=instruction, context=context)
    return generate(prompt)


def _get_filing_summary_sync(
    ticker: str,
    form_type: str,
    fiscal_year: int | None,
) -> dict:
    ticker = ticker.upper()
    if fiscal_year is None:
        fiscal_year = _resolve_fiscal_year(ticker, form_type)
        if fiscal_year is None:
            return {
                "error": (
                    f"No ingested {form_type} filing found for {ticker}. "
                    "Call ingest_company_filings first."
                )
            }

    company_name = get_company_name(ticker)
    fields = {
        field_name: _extract_field(ticker, form_type, fiscal_year, *field_config)
        for field_name, field_config in _FIELDS.items()
    }

    return {"company": f"{company_name} (FY{fiscal_year})", **fields}


async def get_filing_summary(
    ticker: str,
    form_type: str = "10-K",
    fiscal_year: int | None = None,
) -> dict:
    """Generate a structured summary of a SEC filing covering key business, financial, and
    risk information.

    Returns:
        company: Company name and fiscal year
        business_overview: What the company does (from Item 1)
        key_financials: Revenue, net income, key metrics mentioned (from Item 8)
        growth_discussion: Management's view on performance (from Item 7 MD&A)
        top_risks: Top 5 risk factors (from Item 1A)
        outlook: Forward-looking statements and guidance if present
    """
    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(_get_filing_summary_sync, ticker, form_type, fiscal_year)
