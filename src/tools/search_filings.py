"""MCP tool: semantic search across ingested filings."""

from retrieval.search import search as _search


def search_filings(
    query: str,
    ticker: str,
    form_type: str = "10-K",
    fiscal_year: int | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Semantically search SEC filing content and return relevant passages with citations.

    Each result includes the exact text, section name, page number, and relevance score.

    Args:
        query: Natural language query (e.g. 'revenue growth discussion', 'AI investment plans')
        ticker: Company ticker to search within
        form_type: '10-K' or '10-Q'
        fiscal_year: Filter to a specific year (optional)
        top_k: Number of results to return (1-10)

    Returns:
        List of passages with: text, section, page_number, fiscal_year, relevance_score
    """
    top_k = max(1, min(top_k, 10))
    results = _search(
        query, ticker=ticker, form_type=form_type, fiscal_year=fiscal_year, top_k=top_k
    )
    return [
        {
            "text": r.text,
            "section": r.section_name,
            "page_number": r.page_number,
            "fiscal_year": r.fiscal_year,
            "relevance_score": r.score,
        }
        for r in results
    ]
