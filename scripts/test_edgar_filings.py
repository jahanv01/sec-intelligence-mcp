"""Manual smoke test against the real EDGAR submissions API (Issue 2.3 acceptance criteria)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402


def main() -> None:
    filings = get_recent_filings("AAPL", "10-K", 3)
    assert len(filings) == 3, f"expected 3 filings, got {len(filings)}"
    for f in filings:
        assert f.accession_number, "missing accession number"
        print(f"{f.form_type} filed {f.filing_date} ({f.accession_number}) -> {f.primary_doc_url}")
    print("OK: get_recent_filings returned 3 valid 10-K Filing objects")


if __name__ == "__main__":
    main()
