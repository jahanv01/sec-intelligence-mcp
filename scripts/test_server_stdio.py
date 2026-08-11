"""Standalone smoke test: spawns src/server.py over stdio (same transport Claude
Desktop uses) and calls the `ping` tool, exactly like a real MCP client would.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parent.parent / "src" / "server.py"


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools
        print("Tools exposed:", [t.name for t in tools])
        result = await session.call_tool("ping", {})
        text = result.content[0].text
        print("ping ->", text)
        assert text == "pong", f"expected 'pong', got {text!r}"
        print("OK: server responds correctly over stdio")


if __name__ == "__main__":
    asyncio.run(main())
