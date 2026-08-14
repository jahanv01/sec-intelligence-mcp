"""Real smoke test: ingest a real Apple 10-K into real Qdrant (Issue 3.3 acceptance criteria).

Requires Qdrant running locally: docker compose up -d qdrant
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402
from edgar.parser import fetch_and_parse_filing  # noqa: E402
from retrieval.ingest import (  # noqa: E402
    COLLECTION,
    get_qdrant_client,
    ingest_filing,  # noqa: E402
)


def main() -> None:
    filing = get_recent_filings("AAPL", "10-K", 1)[0]
    parsed = fetch_and_parse_filing(filing)

    client = get_qdrant_client()
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)  # start clean so the first call really embeds

    start = time.perf_counter()
    count = ingest_filing(parsed)
    first_elapsed = time.perf_counter() - start
    print(f"First ingest: {count} chunks in {first_elapsed:.1f}s")
    assert 150 <= count <= 500, f"expected 150-500 chunks, got {count}"

    stored = client.count(COLLECTION).count
    print(f"Points stored in Qdrant: {stored}")
    assert stored == count, f"expected {count} points in Qdrant, found {stored}"

    start = time.perf_counter()
    second_count = ingest_filing(parsed)
    second_elapsed = time.perf_counter() - start
    print(f"Second ingest (should skip): {second_count} chunks in {second_elapsed:.2f}s")
    assert second_count == count
    assert second_elapsed < 1.0, "second call should skip embedding, not re-run the pipeline"

    print("OK: ingested within 150-500 chunks, second call skipped re-embedding")


if __name__ == "__main__":
    main()
