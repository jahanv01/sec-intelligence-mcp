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
| `SEC_EDGAR_USER_AGENT` | Optional. Any string of the form `"AppName you@email.com"`; EDGAR just wants a way to identify/contact you |
| `EMBEDDING_MODEL` | Optional. Defaults to `intfloat/e5-base-v2`; no signup needed, downloads from Hugging Face on first use |

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

# EDGAR data layer (each hits the real EDGAR API)
uv run python scripts/test_edgar_lookup.py         # ticker -> CIK, DuckDB-cached
uv run python scripts/test_edgar_filings.py        # recent 10-K filings for a ticker
uv run python scripts/test_edgar_parser.py         # download + clean a real filing
uv run python scripts/test_edgar_sections.py       # section detection + metadata

# Embedding & retrieval pipeline (real model + real Qdrant)
uv run python scripts/test_chunker.py              # section/paragraph chunking
uv run python scripts/test_encoder.py              # E5 embedding shape/latency
uv run python scripts/test_ingest.py               # chunk -> embed -> upsert to Qdrant
uv run python scripts/test_search.py               # semantic search with citations
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


## Progress so far

**Epic 1 — Foundation.** Got the basic plumbing working: a local Python project set up with
`uv`, a minimal MCP server that Claude Desktop can actually connect to and call, environment
config that fails with a clear error if a required key is missing, and Qdrant (the search
database) running locally via Docker.
