"""Real smoke test for the analyze_filing MCP tool (Issue 4.3 acceptance criteria).

Requires Qdrant running with NVDA already ingested, and a real GEMINI_API_KEY in .env.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.analyze_filing import analyze_filing  # noqa: E402


async def main() -> None:
    result = await analyze_filing("What were NVIDIA's main sources of revenue growth?", "NVDA")

    print("Answer:", result["answer"])
    print("Confidence:", result["confidence"])
    print(f"Sources ({len(result['sources'])}):")
    for s in result["sources"]:
        print(f"  - {s['section_name']} (page {s['page_number']}): {s['text'][:80]!r}")

    assert result["answer"], "expected a non-empty answer"
    assert len(result["sources"]) >= 2, f"expected >= 2 sources, got {len(result['sources'])}"
    for s in result["sources"]:
        assert s["section_name"], "source missing section name"

    print("OK: answer generated with >= 2 source citations including section names")


if __name__ == "__main__":
    asyncio.run(main())
