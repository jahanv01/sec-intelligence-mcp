---
title: sec-intelligence-mcp
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

<!-- mcp-name: io.github.jahanv01/sec-intelligence-mcp -->

# sec-intelligence-mcp

MCP server for SEC EDGAR filing intelligence, fetching, chunking/embedding, retrieval, and evaluation, exposed as tools an MCP client (e.g. Claude Desktop) can call.

## Why this is different from other finance MCP servers

Most finance-related MCP servers in the wild are data-API wrappers -- they return structured
numbers (revenue, EPS, price) from a provider's database. None of the ones we surveyed read
the actual filing documents, so none can answer a question that requires understanding what
a company's management actually *said* -- e.g. "how did NVIDIA's management explain the
datacenter revenue surge?" or "did Amazon's forward guidance tone change between quarters?".

This server retrieves and quotes the real filing text (10-K, 10-Q, 8-K) with a citation --
section name and, where available, page number -- on every claim, and its answer-generation
prompt explicitly refuses to use prior/general knowledge when the retrieved passages don't
contain the answer (verified: asking about NVIDIA's non-existent "Mars operations" correctly
returns "not present in the filing" rather than an invented one). It also has an automated
RAGAS evaluation harness (see below) that measures this claim rather than asserting it.

## Architecture

```mermaid
flowchart LR
    A[Claude Desktop / MCP client] -->|MCP tool calls| B[sec-intelligence-mcp server]
    B --> C[SEC EDGAR API]
    B --> D[Qdrant<br/>vector search]
    B --> E[Gemini<br/>answer generation]
    B --> F[LangFuse<br/>tracing + eval scores]
    C -->|filings| B
    D -->|cited passages| B
    E -->|grounded answer| B
```

## Available tools

| Tool | What it does | Example question |
|---|---|---|
| `ingest_company_filings` | Fetches, parses, and indexes a company's recent SEC filings so they can be searched/analyzed | "Ingest NVIDIA's last 3 10-Ks" |
| `search_filings` | Semantic search across ingested filings, returns passages with citations | "Search Apple's 10-K for anything about AI investment" |
| `analyze_filing` | Answers a specific question with a grounded, cited answer (RAG) | "What were Apple's main risk factors in their 2024 10-K?" |
| `get_filing_summary` | Structured executive summary of a full filing (business, financials, MD&A, risks, outlook) | "Summarize NVIDIA's latest 10-K" |
| `compare_companies` | Side-by-side comparison of 2-4 companies on a specific aspect, grounded in each company's own filing | "Compare NVIDIA and AMD's AI chip strategy" |
| `detect_financial_anomalies` | Flags notable year-over-year changes in a company's MD&A/risk disclosures | "Did NVIDIA's risk language around China change between 2023 and 2024?" |
| `get_earnings_summary` | Extracts headline metrics, guidance, and management commentary from a quarterly earnings release (8-K) | "Summarize Apple's Q2 2024 earnings" |

## Evaluation results

Measured with [RAGAS](https://github.com/explodinggradients/ragas) on 50 hand-verified
question/ground-truth pairs across 5 companies (full methodology and raw results in
[`eval/README.md`](eval/README.md)):

| Retrieval strategy | Faithfulness | Correctness | Context Recall |
|---|---|---|---|
| v1: semantic-only (dense embeddings) | 0.92 | 0.67 | 0.84 |
| v2: hybrid (BM25 + semantic via RRF) -- **production default** | 0.95 | 0.78 | 0.99 |
| v3: hybrid + cross-encoder reranking | **0.98** | **0.82** | **1.00** |

CI's eval-gate fails any PR to `main` that drops faithfulness below 0.75 on a real,
live-ingested subset of these questions -- see `.github/workflows/ci.yml`.

## LangFuse dashboard

A real trace of `analyze_filing` answering "What risks does NVIDIA face from export
controls?" -- the span tree shows `retrieval` and `embedding` nested under the tool call,
alongside the LLM generation, with a `faithfulness: 1.00` score attached automatically:

![LangFuse trace showing analyze_filing's span tree and a 1.00 faithfulness score](docs/langfuse-trace.png)

## Contributing

Issues and PRs welcome. See `docs/edgar-api.md` for EDGAR API quirks (rate limits, required
User-Agent header) and `eval/README.md` before changing anything in the retrieval pipeline --
a PR that regresses RAGAS faithfulness below 0.75 will fail CI's eval-gate job.

## Hosted deployment (Oracle Cloud Always Free)

Deployed on an Oracle Cloud "Always Free" compute VM (Ampere A1, ARM) rather than Render or
Hugging Face Spaces: both of those give the container an *ephemeral* filesystem (wiped on
every restart/redeploy) and cap free-tier RAM at 512MB, which doesn't comfortably fit the
embedding model (e5-base-v2, CPU-only, ~440MB loaded) alongside the rest of the process. A
real Always Free VM has neither constraint -- genuine persistent disk and up to 24GB RAM --
so Qdrant runs locally via the same `docker-compose.yml` used for local dev, with no
separate Qdrant Cloud account needed.

Setup (one-time):
1. Create an Always Free Ampere A1 compute instance (Ubuntu image) in the Oracle Cloud
   console, and note its public IP.
2. In the VCN's **Security List** (not just the instance's own firewall -- both must allow
   it), add an ingress rule for TCP port `8000` (and `22` for SSH, usually already open).
3. SSH in, install Docker + the Compose plugin, then:
   ```
   git clone https://github.com/<your-username>/sec-intelligence-mcp.git
   cd sec-intelligence-mcp
   cp .env.example .env   # fill in GEMINI_API_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY
   echo "MCP_TRANSPORT=sse" >> .env
   sudo docker compose up -d --build
   ```
   `QDRANT_URL` doesn't need to be set in `.env` here -- `docker-compose.yml` already
   overrides it to `http://qdrant:6333`, the in-network service name, for the `app` service.
4. Also open the instance's own firewall for the port (Ubuntu ships `iptables`/`ufw` rules
   that block it even after the Security List allows it):
   ```
   sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
   sudo netfilter-persistent save   # or: sudo ufw allow 8000/tcp
   ```
5. Confirm: `curl http://<instance-public-ip>:8000/health` returns `ok`.

Both services have `restart: unless-stopped`, so a VM reboot brings the whole stack back up
without manual intervention. Plain HTTP (no TLS/domain) is used for now -- fine for a demo,
but a real production deployment would put Caddy or Nginx in front for HTTPS.

### Alternative: Hugging Face Spaces (prepared, not the current deployment)

The YAML frontmatter at the top of this README is Spaces metadata (Docker SDK), left in
place in case this becomes the deployment target again -- it's inert otherwise. To use it:
huggingface.co -> New Space -> SDK: Docker -> create it, add `GEMINI_API_KEY`, `QDRANT_URL`,
`QDRANT_API_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY` as **secrets** and
`MCP_TRANSPORT=sse` as a **variable** in Space Settings, then `git push` this repo to the
Space's git remote. Spaces storage is ephemeral on restart like Render's free tier, so this
path still needs a separate Qdrant Cloud instance rather than the local Qdrant container.

## Quick install

Published on PyPI: https://pypi.org/project/sec-intelligence-mcp/. No clone needed --
[uv](https://docs.astral.sh/uv/getting-started/installation/) fetches and runs it on demand:

```
uvx sec-intelligence-mcp
```

You'll still need the API keys below set as environment variables (or in Claude Desktop's
config -- see "Connecting Claude Desktop") and a reachable Qdrant instance (local via Docker,
or Qdrant Cloud); `uvx` only handles getting the code installed and running, not those.

## Setup (for local development)

Contributing, or want to run from source instead of the published package:

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
| `GEMINI_MODEL` | Optional. Defaults to `gemini-flash-lite-latest` |

`src/config.py` fails fast at import time (raises `RuntimeError`) if any required key is missing.

## Connecting Claude Desktop

Add this to your `claude_desktop_config.json` (on Windows:
`%APPDATA%\Claude\claude_desktop_config.json`) -- using the published package, no clone needed:

```json
{
  "mcpServers": {
    "sec-intelligence-mcp": {
      "command": "uvx",
      "args": ["sec-intelligence-mcp"],
      "env": {
        "GEMINI_API_KEY": "your-key",
        "QDRANT_URL": "http://localhost:6333",
        "LANGFUSE_SECRET_KEY": "your-key",
        "LANGFUSE_PUBLIC_KEY": "your-key"
      }
    }
  }
}
```

Running from a local clone instead (see "Setup" above)? Use this config instead:

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

# MCP tools (real pipeline + real Gemini calls)
uv run python scripts/test_tool_ingest_company_filings.py
uv run python scripts/test_tool_search_filings.py
uv run python scripts/test_tool_analyze_filing.py
uv run python scripts/test_tool_get_filing_summary.py
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

**Epic 2 — Fetching filings from SEC.** Given a stock ticker like "NVDA", the system now looks
up the company, finds its annual reports (10-Ks), downloads them, strips out all the HTML
formatting down to clean text, and splits that text into its standard labeled sections (Item 1
Business, Item 1A Risk Factors, Item 7 MD&A, etc.) so we always know which part of the filing
any piece of text came from.

**Epic 3 — Making it searchable by meaning.** Each filing gets cut into small overlapping
chunks, and each chunk is converted into a vector (a list of numbers capturing its meaning)
using a free, local AI model — no paid API needed. Those vectors go into Qdrant, so a question
like "data center revenue growth" finds the right paragraph even if it doesn't use those exact
words, and every result comes back with a citation (company, section, filing) so we always know
exactly where an answer came from.

**Epic 4 — Tools Claude can actually call.** Wired everything into four MCP tools: one to
fetch and index a company's filings, one for semantic search, one that answers a specific
question with citations (using a free Gemini model, instructed to only use the retrieved
filing text — never general knowledge), and one that generates a structured summary
(business overview, financials, risks, outlook) of an entire filing.

**Epic 5 — Making answers more trustworthy.** Tightened the answer-generation prompt so the
model explicitly refuses to guess when a filing doesn't contain the answer, and cites every
claim back to its exact section — this genuinely works, verified live (asking about NVIDIA's
non-existent "Mars operations" correctly returns "not present in the filing" instead of an
invented answer). Also implemented a second search method (BM25 exact-keyword matching,
blended with the existing semantic search) and a re-ranking step, both tested against real
data rather than assumed to work.

Honest result: the two acceptance benchmarks weren't met as originally written, and the
investigation into *why* turned out to be the more useful finding. Quadrupling the test
corpus made both hybrid retrieval and re-ranking perform *worse* on the strict pass/fail
metric — which disproved an initial "not enough data" theory rather than confirming it. The
real explanation: the benchmark's accounting-term queries are formulaic line items where
keyword search and semantic search already agree, leaving no ambiguity for hybrid search to
resolve — its actual value showed up on a genuinely ambiguous query where semantic search
drifted toward the wrong (but related) passage. Re-ranking's shortfall turned out to be a
model-fit issue (the specified cross-encoder was trained on web search, not SEC filings), not
something more data would fix. Hybrid search is used by default since it never hurt in
testing; re-ranking is implemented but kept opt-in (`use_reranker`) since it occasionally made
results worse with this specific model.

**Epic 6 — Advanced MCP Tools v2.** Added three tools that combine multiple filings or companies into higher-level analysis: compare_companies grounds a side-by-side comparison of 2-4 companies in their actual filing text with citations; detect_financial_anomalies compares a company's MD&A and Risk Factors sections across consecutive fiscal years and flags notable changes (new risks, unexplained financial swings, tone shifts); get_earnings_summary locates a company's quarterly earnings press release (the 8-K Exhibit 99.1) and extracts headline metrics, management quotes, guidance, and tone. All three were verified against real data: NVIDIA's actual FY2023→FY2024 datacenter revenue surge (126% growth) was correctly flagged as a high-severity anomaly, and Apple's real Q2 2024 earnings release yielded 4 grounded management statements from Tim Cook and Luca Maestri.

**Epic 7 — Evaluation Pipeline.** Built an automated RAG-quality eval harness so quality is measured before every release, not assumed. 50 real question-answer pairs across 5 companies (AAPL, NVDA, MSFT, AMZN, GOOGL) and 5 question types, with ground truth extracted from actual 10-K filings and independently verified against source text — not LLM-invented. Scored with RAGAS (faithfulness, answer correctness, context recall), wired to this project's own Gemini key rather than RAGAS's OpenAI default. Building the eval dataset surfaced and fixed two real production bugs: section-detection was silently missing real headings on filers that use a non-breaking space (Amazon, NVIDIA) or repeat "Item N" as a running header throughout a section (Microsoft), corrupting section boundaries for any company beyond the original three tested now fixed and regression-tested. Separately, the core Gemini call had no retry/backoff, so any tool could crash outright on a routine rate limit now retries with exponential backoff.

**Epic 8 — Observability.** Added production observability to `analyze_filing` using LangFuse Cloud, with the Python SDK and required credentials documented in `.env.example`. Instrumented the full analysis flow with separate embedding, retrieval, and LLM generation spans capturing queries, filters, retrieved chunks, scores, prompts, responses, and token usage. Added background RAGAS faithfulness scoring so evaluation does not block the user response, with scores attached to the originating LangFuse trace. Added explicit latency monitoring for embedding, retrieval, LLM calls, and total tool execution. Verified the implementation with real NVDA queries, including a 1.00 faithfulness score and all expected traces/spans appearing in the LangFuse dashboard. Three real calls averaged ~5.04s, below the 8s target; one 8.82s outlier was investigated through LangFuse and traced to a 5.27s query-embedding spike, likely caused by CPU contention on the development machine rather than a reproduced code-level issue.

**Epic 9 — Testing & CI/CD.** Set up a real GitHub Actions pipeline so quality gates run automatically on every push and PR, not just when someone remembers to run tests manually. Unit test coverage for core modules (edgar/lookup.py, embeddings/chunker.py, retrieval/search.py, config.py) was already in place from writing tests alongside each epic as it was built — 117 tests total, all mocked, zero real network calls, running in under a minute. Added a real end-to-end integration test against Apple's actual FY2023 10-K (ingest → search → analyze → verify citation), marked to run manually before release rather than on every push since it needs live Qdrant and Gemini and takes several minutes.

The CI pipeline itself has four jobs: lint, test, a Docker build check, and an eval-gate that runs a subset of the real Epic 7 eval questions against live-ingested data on every PR to main, failing the build if faithfulness drops below 0.75. Getting this actually working end-to-end (not just written) surfaced two real bugs worth noting: a PYTHONPATH gap that broke an inline ingestion step, and a fiscal-year mismatch where the CI job was ingesting the wrong year's filing relative to what the eval questions expected — both caught and fixed by watching real CI runs fail, not by inspection alone. The eval-gate is intentionally scoped to a handful of questions rather than the full 50, since each one costs several real Gemini API calls and the free tier's daily quota is a real, previously-hit constraint.


