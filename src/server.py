"""MCP server entrypoint for sec-intelligence-mcp."""

from mcp.server.fastmcp import FastMCP

from tools.analyze_filing import analyze_filing
from tools.compare_companies import compare_companies
from tools.detect_financial_anomalies import detect_financial_anomalies
from tools.get_filing_summary import get_filing_summary
from tools.ingest_company_filings import ingest_company_filings
from tools.search_filings import search_filings

mcp = FastMCP("sec-intelligence-mcp")


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


if __name__ == "__main__":
    mcp.run()
