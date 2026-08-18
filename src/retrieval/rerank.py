"""Cross-encoder re-ranking: scores query-document pairs directly for much more accurate
relevance than cosine similarity, at the cost of being too slow to run over a whole corpus --
so it only ever re-scores a small candidate set already narrowed down by retrieval.
"""

from sentence_transformers import CrossEncoder

from retrieval.search import RetrievedChunk

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Loaded eagerly at import time, not lazily -- see embeddings/encoder.py for why (loading a
# sentence-transformers model on first use, after the MCP server's event loop is already
# running, hung indefinitely on this machine; loading before the event loop starts works).
_model = CrossEncoder(CROSS_ENCODER_MODEL)


def rerank(query: str, chunks: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
    """Re-scores each chunk against the query with a cross-encoder and returns the top_k,
    reordered best-first. chunk.score is replaced with the cross-encoder's relevance score."""
    if not chunks:
        return []

    pairs = [(query, c.text) for c in chunks]
    scores = _model.predict(pairs)

    reranked = sorted(zip(chunks, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [chunk.model_copy(update={"score": float(score)}) for chunk, score in reranked[:top_k]]
