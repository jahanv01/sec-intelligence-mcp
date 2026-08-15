"""MCP tool: fetch, parse, and ingest a company's filings so they can be searched."""

from mcp.server.fastmcp import Context

from edgar.filings import get_recent_filings
from edgar.lookup import get_cik, get_company_name
from edgar.parser import fetch_and_parse_filing
from retrieval.ingest import ingest_filing


async def ingest_company_filings(
    ticker: str,
    form_type: str = "10-K",
    years: int = 3,
    ctx: Context | None = None,
) -> str:
    """Fetch and index SEC filings for a company so they can be searched and analyzed.

    Must be called before using analyze_filing or search_filings for a new company.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'MSFT')
        form_type: Filing type — '10-K' (annual) or '10-Q' (quarterly)
        years: Number of recent filings to ingest (1-5)

    Returns:
        Summary of ingested filings with filing dates and chunk counts
    """
    ticker = ticker.upper()
    try:
        get_cik(ticker)  # validate before making any EDGAR call
    except ValueError:
        return f"Unknown ticker: {ticker}. Use a valid US stock ticker."

    years = max(1, min(years, 5))
    company_name = get_company_name(ticker)

    filings = get_recent_filings(ticker, form_type, limit=years)
    if not filings:
        return f"No {form_type} filings found for {ticker}."

    rows: list[tuple[str, int | None, int]] = []
    for i, filing in enumerate(filings, start=1):
        if ctx:
            await ctx.info(
                f"Processing {ticker} {form_type} filed {filing.filing_date} ({i}/{len(filings)})"
            )
        parsed = fetch_and_parse_filing(filing)
        chunk_count = ingest_filing(parsed)
        rows.append((filing.filing_date, parsed.fiscal_year, chunk_count))

    total_chunks = sum(r[2] for r in rows)
    years_covered = sorted({r[1] for r in rows if r[1] is not None})
    coverage = f"FY{years_covered[0]}-FY{years_covered[-1]}" if years_covered else "unknown"

    lines = [f"Ingested {len(filings)} {form_type} filing(s) for {company_name} ({ticker}):"]
    for filing_date, fiscal_year, chunk_count in rows:
        lines.append(f"  - FY{fiscal_year}, filed {filing_date}: {chunk_count} chunks")
    lines.append(f"Total chunks indexed: {total_chunks}")
    lines.append(f"Coverage: {coverage}. Ready for search_filings / analyze_filing.")
    return "\n".join(lines)
