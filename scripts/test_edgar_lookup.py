"""Manual smoke test against the real EDGAR ticker file (Issue 2.2 acceptance criteria)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edgar import lookup  # noqa: E402


def main() -> None:
    lookup.DB_PATH.unlink(missing_ok=True)  # start clean so the first call really hits the network

    start = time.perf_counter()
    cik = lookup.get_cik("NVDA")
    first_call_seconds = time.perf_counter() - start
    print(f"First call (network fetch): get_cik('NVDA') -> {cik} in {first_call_seconds:.2f}s")
    assert cik == "0001045810", f"expected 0001045810, got {cik}"

    start = time.perf_counter()
    cik2 = lookup.get_cik("NVDA")
    second_call_seconds = time.perf_counter() - start
    print(f"Second call (cached): get_cik('NVDA') -> {cik2} in {second_call_seconds:.3f}s")
    assert cik2 == cik
    assert second_call_seconds < 0.5, "second call should be cache-only, not a network fetch"

    print("Company name:", lookup.get_company_name("AAPL"))
    print("OK: ticker->CIK lookup + DuckDB cache work correctly")


if __name__ == "__main__":
    main()
