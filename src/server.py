"""MCP server entrypoint for sec-intelligence-mcp."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sec-intelligence-mcp")


@mcp.tool()
def ping() -> str:
    """Health-check tool. Returns 'pong' if the server is reachable."""
    return "pong"


if __name__ == "__main__":
    mcp.run()
