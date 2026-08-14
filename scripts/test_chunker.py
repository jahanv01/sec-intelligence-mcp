"""Manual smoke test against a real Apple 10-K (Issue 3.1 acceptance criteria)."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402
from edgar.parser import fetch_and_parse_filing  # noqa: E402
from embeddings.chunker import chunk_filing  # noqa: E402


def main() -> None:
    filing = get_recent_filings("AAPL", "10-K", 1)[0]
    parsed = fetch_and_parse_filing(filing)

    chunks = chunk_filing(parsed)
    levels = Counter(c.chunk_level for c in chunks)
    print(
        f"Total chunks: {len(chunks)} (section={levels['section']}, paragraph={levels['paragraph']})"
    )

    for c in chunks[:3]:
        print(f"  [{c.chunk_level}] {c.section_name} @ {c.char_start}: {c.text[:60]!r}")

    assert 150 <= len(chunks) <= 500, f"expected 150-500 chunks, got {len(chunks)}"
    for c in chunks:
        assert c.ticker and c.form_type and c.fiscal_year and c.section_name and c.accession_number

    print("OK: chunk count in range with complete metadata on every chunk")


if __name__ == "__main__":
    main()
