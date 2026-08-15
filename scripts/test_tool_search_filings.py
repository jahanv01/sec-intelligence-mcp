"""Real smoke test for the search_filings MCP tool (Issue 4.2 acceptance criteria).

Requires Qdrant running with NVDA already ingested (see scripts/test_ingest.py or
scripts/test_tool_ingest_company_filings.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.search_filings import search_filings  # noqa: E402


def main() -> None:
    results = search_filings("data center revenue", "NVDA")
    print(f"Got {len(results)} results")
    for r in results:
        print(f"  score={r['relevance_score']:.3f} section={r['section']} text={r['text'][:80]!r}")

    assert results, "expected at least one result"
    for r in results:
        assert set(r.keys()) == {"text", "section", "page_number", "fiscal_year", "relevance_score"}

    top = results[0]
    assert top["section"] == "Item 7", f"expected Item 7, got {top['section']}"
    assert top["relevance_score"] > 0.7, f"expected > 0.7, got {top['relevance_score']}"

    print(f"OK: top result from {top['section']} scoring {top['relevance_score']:.3f}")


if __name__ == "__main__":
    main()
