"""Real smoke test: semantic search against a real NVDA 10-K (Issue 3.4 acceptance criteria).

Requires Qdrant running locally: docker compose up -d qdrant
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402
from edgar.parser import fetch_and_parse_filing  # noqa: E402
from retrieval.ingest import ingest_filing  # noqa: E402
from retrieval.search import search  # noqa: E402


def main() -> None:
    filing = get_recent_filings("NVDA", "10-K", 1)[0]
    parsed = fetch_and_parse_filing(filing)
    ingest_filing(parsed)

    results = search("data center revenue growth", ticker="NVDA", top_k=5)
    print(f"Got {len(results)} results")
    for r in results:
        print(
            f"  score={r.score:.3f} section={r.section_name} ticker={r.ticker} text={r.text[:80]!r}"
        )

    assert results, "expected at least one result"
    for r in results:
        assert r.text and r.section_name and r.accession_number and r.ticker
        assert r.ticker == "NVDA", "filter should exclude other tickers"

    top = results[0]
    assert top.score > 0.7, f"expected top score > 0.7, got {top.score}"
    assert top.section_name == "Item 7", f"expected top result from Item 7, got {top.section_name}"

    # sanity check: same query without a ticker filter should never return a different company
    apple_leak = [
        r for r in search("data center revenue growth", ticker="NVDA") if r.ticker != "NVDA"
    ]
    assert not apple_leak, "ticker filter leaked results from another company"

    print(f"OK: top result score={top.score:.3f} from {top.section_name}")


if __name__ == "__main__":
    main()
