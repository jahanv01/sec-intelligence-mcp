"""Embedding pipeline using a sentence-transformers E5-family model (CPU-only).

E5 models were trained to expect a "query: " or "passage: " prefix on the input text --
mixing this up (or omitting it) measurably hurts retrieval quality, since the model learned
different representations for the two roles.
"""

import shutil
import time
from pathlib import Path

import numpy as np
from huggingface_hub import constants as hf_constants
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
# backend="torch" pinned explicitly: sentence-transformers' default backend="auto" can
# mis-detect the ONNX backend on models (like e5-base-v2) whose HF repo also ships onnx/
# and openvino/ variants, and fails in a way that leaves the model silently broken (first
# submodule ends up None) rather than raising a clear error, when onnxruntime isn't
# installed. Forcing "torch" makes it load the actual pytorch_model.bin/safetensors weights.
#
# Retry-with-cache-clear: on an arm64 deployment (Oracle Cloud), this load intermittently
# raised "AttributeError: 'NoneType' object has no attribute 'parameters'" from deep inside
# SentenceTransformer's module construction -- not reproducible in isolation (the identical
# call, run standalone, consistently succeeded), so most likely a corrupted/incomplete
# download or a native-library race rather than a real code bug. Root cause not confirmed;
# this treats it as transient and retries against a clean cache rather than blocking release
# on further diagnosis. If this still fails after all attempts, it raises for real.
def _load_model(retries: int = 3, delay_seconds: float = 5.0) -> SentenceTransformer:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return SentenceTransformer(EMBEDDING_MODEL, device="cpu", backend="torch")
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, see comment above
            last_error = exc
            cache_dir = Path(hf_constants.HF_HUB_CACHE)
            model_cache = cache_dir / ("models--" + EMBEDDING_MODEL.replace("/", "--"))
            shutil.rmtree(model_cache, ignore_errors=True)
            if attempt < retries:
                time.sleep(delay_seconds)
    raise RuntimeError(
        f"Failed to load embedding model {EMBEDDING_MODEL!r} after {retries} attempts"
    ) from last_error


_model = _load_model()


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
