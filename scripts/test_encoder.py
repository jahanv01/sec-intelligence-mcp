"""Real-model smoke test for embeddings/encoder.py (Issue 3.2 acceptance criteria)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from embeddings.encoder import encode, encode_passages, encode_query  # noqa: E402


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> None:
    # warm up: model loading (and any first-run download) shouldn't count against the
    # "under 100ms" encode-latency acceptance bar.
    encode(["passage: warmup"])

    start = time.perf_counter()
    result = encode(["passage: Apple reported revenue of $385B"])
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"encode() shape: {result.shape}, elapsed: {elapsed_ms:.1f}ms")
    assert result.shape == (1, 768), f"expected (1, 768), got {result.shape}"
    assert elapsed_ms < 100, f"expected < 100ms, got {elapsed_ms:.1f}ms"

    query_vec = encode_query("data center revenue growth")
    relevant, irrelevant = encode_passages(
        [
            "Data center revenue increased significantly driven by AI accelerator demand.",
            "The weather in Cupertino was mild throughout the fiscal year.",
        ]
    )
    sim_relevant = _cosine(query_vec, relevant)
    sim_irrelevant = _cosine(query_vec, irrelevant)
    print(f"cosine(query, relevant passage)   = {sim_relevant:.3f}")
    print(f"cosine(query, irrelevant passage) = {sim_irrelevant:.3f}")
    assert sim_relevant > sim_irrelevant, "relevant passage should score higher than irrelevant"

    print("OK: encode() shape/latency correct, and embeddings rank relevant text higher")


if __name__ == "__main__":
    main()
