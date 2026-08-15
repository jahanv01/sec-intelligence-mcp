"""Real smoke test for the get_filing_summary MCP tool (Issue 4.4 acceptance criteria).

Requires Qdrant running with AAPL already ingested, and a real GEMINI_API_KEY in .env.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.get_filing_summary import get_filing_summary  # noqa: E402


def main() -> None:
    result = get_filing_summary("AAPL", "10-K")

    for field, value in result.items():
        print(f"--- {field} ---")
        print(value)
        print()

    expected_fields = {
        "company",
        "business_overview",
        "key_financials",
        "growth_discussion",
        "top_risks",
        "outlook",
    }
    assert set(result.keys()) == expected_fields, (
        f"missing fields: {expected_fields - result.keys()}"
    )
    for field, value in result.items():
        assert value, f"{field} is empty"

    print("OK: all 6 fields present with non-empty content")


if __name__ == "__main__":
    main()
