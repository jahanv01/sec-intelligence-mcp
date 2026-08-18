"""Environment configuration. Fails fast at import time if required keys are missing."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Must be set before sentence_transformers/huggingface_hub are imported anywhere. When the
# MCP server runs as a stdio subprocess (e.g. spawned by Claude Desktop), tqdm's progress bar
# and huggingface_hub's HTTP debug logging write a burst of output to stderr during model
# loading; on Windows this can overwhelm the async subprocess pipe faster than the parent
# drains it and deadlock the whole stdio transport. A real server has no use for that output
# either way.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# torch bundles its own OpenMP/MKL runtime DLL. When other native-extension libraries this
# server also imports (grpc via qdrant-client, duckdb) load a same-named runtime DLL first,
# torch's later attempt to initialize its own copy can deadlock instead of erroring, only
# when torch is imported after those -- which is exactly what happens the first time a tool
# lazily loads the embedding model mid-server, after qdrant/duckdb are already imported. This
# is Intel's documented escape hatch for that duplicate-runtime scenario.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

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
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None  # optional for local Qdrant
LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]

# Optional: SEC EDGAR requires an identifying User-Agent ("AppName contact@email.com") or it
# returns 403. Not fail-fast since a sensible default works for local dev.
SEC_EDGAR_USER_AGENT = os.getenv("SEC_EDGAR_USER_AGENT", "sec-intelligence-mcp dev@example.com")

# Optional: which sentence-transformers model to embed with. e5-base-v2 (768-dim, CPU-only,
# 110M params) is the default; bge-base-en-v1.5 is a same-family drop-in alternative.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-base-v2")

# If the model is already cached locally, skip huggingface_hub's "is there a newer revision"
# network check entirely. That check proved unreliable when this server runs as a stdio
# subprocess: MCP clients only pass a restricted env var whitelist to spawned servers (see
# the MCP SDK's get_default_environment()), which can drop proxy settings a network call
# needs -- it then hangs indefinitely instead of failing fast, taking the whole tool call
# down with it. Offline mode is also just better practice for a production server: no
# runtime dependency on huggingface.co being reachable once the model is cached.
_hf_cache_dir = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
_model_cache_name = "models--" + EMBEDDING_MODEL.replace("/", "--")
if (_hf_cache_dir / _model_cache_name).exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Optional: Gemini model for answer generation/summarization. "-latest" aliases track
# whatever Google currently recommends, so this doesn't need updating as specific dated
# model versions get deprecated.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
