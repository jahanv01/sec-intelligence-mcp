"""Embedding pipeline using a sentence-transformers E5-family model (CPU-only).

E5 models were trained to expect a "query: " or "passage: " prefix on the input text --
mixing this up (or omitting it) measurably hurts retrieval quality, since the model learned
different representations for the two roles.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def encode(texts: list[str]) -> np.ndarray:
    """Embed already-prefixed passage texts. Returns shape (len(texts), dim)."""
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def encode_query(query: str) -> np.ndarray:
    """Embed a single search query. Returns shape (dim,)."""
    return encode([f"query: {query}"])[0]


def encode_passages(texts: list[str]) -> np.ndarray:
    """Embed document/chunk texts for indexing. Returns shape (len(texts), dim)."""
    return encode([f"passage: {t}" for t in texts])
