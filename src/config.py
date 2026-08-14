"""Environment configuration. Fails fast at import time if required keys are missing."""

import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "GEMINI_API_KEY",
    "QDRANT_URL",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
]

_missing = [name for name in REQUIRED_VARS if not os.getenv(name)]
if _missing:
    raise RuntimeError(
        "Missing required environment variable(s): "
        f"{', '.join(_missing)}. Copy .env.example to .env and fill in the values."
    )

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # optional for local Qdrant
LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]

# Optional: SEC EDGAR requires an identifying User-Agent ("AppName contact@email.com") or it
# returns 403. Not fail-fast since a sensible default works for local dev.
SEC_EDGAR_USER_AGENT = os.getenv("SEC_EDGAR_USER_AGENT", "sec-intelligence-mcp dev@example.com")

# Optional: which sentence-transformers model to embed with. e5-base-v2 (768-dim, CPU-only,
# 110M params) is the default; bge-base-en-v1.5 is a same-family drop-in alternative.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-base-v2")
