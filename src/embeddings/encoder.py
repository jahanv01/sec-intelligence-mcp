"""Embedding pipeline using a sentence-transformers E5-family model (CPU-only).

E5 models were trained to expect a "query: " or "passage: " prefix on the input text --
mixing this up (or omitting it) measurably hurts retrieval quality, since the model learned
different representations for the two roles.
"""

import numpy as np
from langfuse import observe
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL

# Loaded eagerly, synchronously, at import time -- deliberately, not lazily. Loading this on
# first use instead (whether inline or via a background thread) meant the import started
# after the MCP server's asyncio event loop was already running, which hung indefinitely
# rather than completing -- torch/sentence_transformers appear to conflict with something in
# that active-event-loop context on this machine (root cause not fully identified; see git
# history on this file for the investigation). Blocking here, before the event loop starts at
# all, is the one approach confirmed to actually complete. It costs several seconds to ~1
# minute of server startup time (first run after install can take longer -- one-time
# antivirus scan of newly-installed files).
_model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def encode(texts: list[str]) -> np.ndarray:
    """Embed already-prefixed passage texts. Returns shape (len(texts), dim)."""
    return _model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


@observe(name="embedding", as_type="embedding")
def encode_query(query: str) -> np.ndarray:
    """Embed a single search query. Returns shape (dim,).

    Traced separately from the rest of retrieval (Issue 8.3) -- not encode_passages, which
    runs during ingestion and would otherwise create a trace per chunk, out of this epic's
    scope.

    Latency note: normally ~100ms on this CPU-only model, but real traces showed an
    occasional spike to 5+ seconds (once in 3 real analyze_filing calls) that was the sole
    cause of a call exceeding the 8s target -- retrieval's non-embedding work and the LLM
    call stayed consistent across both the slow and fast runs. Whatever else is running on
    the machine at call time (this dev box also runs Docker/Qdrant) appears to intermittently
    starve this CPU-bound inference call; not reproduced as a deterministic code bug.
    """
    return encode([f"query: {query}"])[0]


def encode_passages(texts: list[str]) -> np.ndarray:
    """Embed document/chunk texts for indexing. Returns shape (len(texts), dim)."""
    return encode([f"passage: {t}" for t in texts])
