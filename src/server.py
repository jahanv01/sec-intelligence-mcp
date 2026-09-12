"""MCP server entrypoint for sec-intelligence-mcp."""

import os
import sys

# Must import before anything else in this file (mcp/starlette/tools/*). Deep-diagnosed on
# an arm64 deployment: loading sentence-transformers' model at the bottom of the real import
# chain (server -> tools.analyze_filing -> retrieval.hybrid -> retrieval.ingest ->
# embeddings.encoder) reliably crashed with "AttributeError: 'NoneType' object has no
# attribute 'parameters'" inside SentenceTransformer.__init__ -- yet the exact same model
# load, run standalone or after manually replaying every other import in this chain
# individually, always succeeded. The one remaining difference is import depth/order itself;
# loading it first here, before anything else, reproduces the working case instead.
import embeddings.encoder  # noqa: F401,E402,I001 -- isort: skip

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

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
    # Only relevant for the "sse"/"streamable-http" transports -- ignored under stdio.
    # 0.0.0.0 so the container's port mapping can reach it; Render sets $PORT at runtime.
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> PlainTextResponse:
    """Plain-HTTP health check for the sse/streamable-http transports (e.g. Render)."""
    return PlainTextResponse("ok")


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


def main() -> None:
    # --transport sse|stdio overrides MCP_TRANSPORT overrides the stdio default, so local
    # Claude Desktop usage (stdio, no flags) is unaffected by the Render deployment path.
    transport = "stdio"
    if "--transport" in sys.argv:
        transport = sys.argv[sys.argv.index("--transport") + 1]
    else:
        transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
