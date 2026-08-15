"""Standalone smoke test: spawns src/server.py over stdio (same transport Claude
Desktop uses) and calls the `ping` tool, exactly like a real MCP client would.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parent.parent / "src" / "server.py"


EXPECTED_TOOLS = {
    "ping",
    "ingest_company_filings",
    "search_filings",
    "analyze_filing",
    "get_filing_summary",
}


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools
        tool_names = {t.name for t in tools}
        print("Tools exposed:", sorted(tool_names))
        assert tool_names >= EXPECTED_TOOLS, f"missing tools: {EXPECTED_TOOLS - tool_names}"

        result = await session.call_tool("ping", {})
        text = result.content[0].text
        print("ping ->", text)
        assert text == "pong", f"expected 'pong', got {text!r}"

        # exercise a real tool (not just ping) over the actual protocol, against
        # already-ingested NVDA data
        result = await session.call_tool(
            "search_filings", {"query": "data center revenue", "ticker": "NVDA"}
        )
        print("search_filings ->", result.content[0].text[:200])
        assert not result.isError, f"search_filings tool call failed: {result.content}"

        print("OK: server responds correctly over stdio, all tools registered and callable")


if __name__ == "__main__":
    asyncio.run(main())
