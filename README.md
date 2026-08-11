# sec-intelligence-mcp

MCP server for SEC EDGAR filing intelligence — fetching, chunking/embedding, retrieval, and
evaluation, exposed as tools an MCP client (e.g. Claude Desktop) can call.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Install dependencies:
   ```
   uv sync
   ```
3. Copy `.env.example` to `.env` and fill in the keys (see below).
4. Start Qdrant locally:
   ```
   docker compose up -d qdrant
   ```
5. Run the server directly:
   ```
   uv run python src/server.py
   ```
   Or with the MCP Inspector (dev UI, requires Node.js):
   ```
   uv run mcp dev src/server.py
   ```

## Running via Docker

`docker compose up -d` builds the server image and starts it alongside Qdrant. The `app`
service reads secrets from your local `.env` via `env_file`, and `QDRANT_URL` is overridden
to `http://qdrant:6333` (the in-network service name) since `localhost` inside the container
would not reach the `qdrant` container. `config.py` still fails fast if `.env` is missing
required keys.

## Getting API keys (all free)

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey — free tier, sign in with Google account |
| `QDRANT_URL` | `http://localhost:6333` when running Qdrant via `docker compose up -d qdrant` (no signup needed) |
| `QDRANT_API_KEY` | Only needed for a hosted Qdrant Cloud instance; leave blank for local |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` | https://cloud.langfuse.com — free tier, create a project, copy keys from Settings → API Keys |

`src/config.py` fails fast at import time (raises `RuntimeError`) if any required key is missing.

## Connecting Claude Desktop

Add this to your `claude_desktop_config.json` (on Windows:
`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sec-intelligence-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\ABSOLUTE\\PATH\\TO\\sec-intelligence-mcp",
        "run",
        "python",
        "src/server.py"
      ]
    }
  }
}
```

Restart Claude Desktop, open the tools list, and confirm `sec-intelligence-mcp` appears with a
`ping` tool that returns `"pong"`.

## Testing locally

```
uv run python -c "import mcp"                    # SDK installed correctly
uv run python scripts/test_server_stdio.py        # server responds over stdio (ping -> pong)
docker compose up -d qdrant
uv run python scripts/test_qdrant.py               # Qdrant round-trip works
```

## Project structure

```
src/
├── server.py        # MCP server entrypoint
├── tools/            # One file per MCP tool
├── edgar/            # SEC EDGAR fetching + parsing
├── embeddings/        # Chunking + embedding pipeline
├── retrieval/         # Qdrant client + search
├── evaluation/         # RAGAS eval pipeline
└── config.py          # Env var loading (fail-fast)
tests/                  # Unit/integration tests
prompts/                # Prompt templates (.txt)
data/                   # Gitignored local cache (DuckDB, filing PDFs, Qdrant storage)
eval/                   # Test questions + ground truth answers
scripts/                # One-off dev/test scripts
```
