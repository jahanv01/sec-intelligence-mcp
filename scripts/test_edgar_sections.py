"""Manual smoke test against a real Apple 10-K (Issue 2.5 acceptance criteria)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar.filings import get_recent_filings  # noqa: E402
from edgar.parser import fetch_and_parse_filing  # noqa: E402
from edgar.sections import extract_metadata, parse_and_store_sections  # noqa: E402


def main() -> None:
    filing = get_recent_filings("AAPL", "10-K", 1)[0]
    parsed = fetch_and_parse_filing(filing)

    result = parse_and_store_sections(parsed)
    names = {s.section_name for s in result}
    print(f"Detected {len(result)} sections: {sorted(names)}")
    for s in result:
        preview = s.section_text[:80].replace("\n", " ")
        print(f"  {s.section_name}: [{s.char_start}:{s.char_end}] {preview!r}")

    assert len(result) >= 8, f"expected >= 8 sections, got {len(result)}"
    assert "Item 1A" in names, "Item 1A not detected"
    assert "Item 7" in names, "Item 7 not detected"
    # Some items are legitimately tiny in real filings (e.g. "Item 1B... None." or
    # "Item 6... [Reserved]"), so this only catches outright-empty detection failures.
    assert all(len(s.section_text) > 10 for s in result), "a section is suspiciously empty"

    metadata = extract_metadata(parsed.raw_text)
    print("Metadata:", metadata)

    print(f"OK: detected {len(result)} sections including Item 1A and Item 7")


if __name__ == "__main__":
    main()
