"""Manual smoke test against a real Apple 10-K (Issue 2.4 acceptance criteria)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402
from edgar.parser import fetch_and_parse_filing  # noqa: E402


def main() -> None:
    filing = get_recent_filings("AAPL", "10-K", 1)[0]
    parsed = fetch_and_parse_filing(filing)

    print(f"Accession: {parsed.accession_number}")
    print(f"Characters: {len(parsed.raw_text):,}")
    print("Preview:", parsed.raw_text[:200].replace("\n", " "))

    assert len(parsed.raw_text) >= 50_000, f"expected >= 50,000 chars, got {len(parsed.raw_text):,}"
    print("OK: parsed filing has at least 50,000 characters of clean text")


if __name__ == "__main__":
    main()
