"""End-to-end integration test against a real fixture filing (Issue 9.2).

Needs real Qdrant + Gemini infra, so it's marked @pytest.mark.integration and excluded
from CI's default test run (see .github/workflows/ci.yml's `-m "not integration"`).
Run manually before release:
    uv run pytest tests/test_integration.py -m integration -v
"""

import json
from pathlib import Path

import pytest

from edgar.parser import ParsedFiling
from retrieval.hybrid import hybrid_search
from retrieval.ingest import ingest_filing
from tools.analyze_filing import analyze_filing

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "aapl_fy2023_10k.json"


def _load_fixture() -> ParsedFiling:
    return ParsedFiling(**json.loads(FIXTURE_PATH.read_text()))


@pytest.mark.integration
async def test_ingest_search_and_analyze_end_to_end():
    parsed = _load_fixture()

    # Ingest -- idempotent (deterministic chunk IDs), safe to re-run against real infra.
    chunk_count = ingest_filing(parsed)
    assert chunk_count > 0

    # Search -- verify retrieval finds real, correctly-tagged chunks from this filing.
    results = hybrid_search(
        "What were Apple's main products and services in fiscal year 2023?",
        ticker="AAPL",
        form_type="10-K",
        fiscal_year=2023,
    )
    assert results, "expected retrieval to find at least one chunk from the ingested fixture"
    for r in results:
        assert r.section_name
        assert r.ticker == "AAPL"
        assert r.fiscal_year == 2023

    # Analyze -- verify the full RAG answer is grounded with a citation.
    result = await analyze_filing(
        "What were Apple's main sources of revenue in fiscal year 2023?",
        "AAPL",
        fiscal_year=2023,
    )
    assert result["sources"]
    assert "[Section:" in result["answer"], (
        f"expected at least one [Section: ...] citation in the answer, got: {result['answer']!r}"
    )
