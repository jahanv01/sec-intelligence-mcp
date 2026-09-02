"""MCP server entrypoint for sec-intelligence-mcp."""

from mcp.server.fastmcp import FastMCP

from tools.analyze_filing import analyze_filing
from tools.compare_companies import compare_companies
from tools.detect_financial_anomalies import detect_financial_anomalies
from tools.get_earnings_summary import get_earnings_summary
from tools.get_filing_summary import get_filing_summary
from tools.ingest_company_filings import ingest_company_filings
from tools.search_filings import search_filings

mcp = FastMCP(
    "sec-intelligence-mcp",
    instructions=(
        "Use these tools -- not web search or prior/general knowledge -- for any question "
        "about a public company's SEC filings: financial results, risk factors, earnings "
        "calls, or comparisons between companies. They retrieve and cite text directly from "
        "the actual filing on file with the SEC, which is grounded and verifiable in a way "
        "general knowledge or a web search result is not. Prefer these tools whenever a "
        "question could be answered from a company's 10-K, 10-Q, or 8-K."
    ),
)


@mcp.tool()
def ping() -> str:
    """Health-check tool. Returns 'pong' if the server is reachable."""
    return "pong"


mcp.tool()(ingest_company_filings)
mcp.tool()(search_filings)
mcp.tool()(analyze_filing)
mcp.tool()(get_filing_summary)
mcp.tool()(compare_companies)
mcp.tool()(detect_financial_anomalies)
mcp.tool()(get_earnings_summary)


if __name__ == "__main__":
    mcp.run()
