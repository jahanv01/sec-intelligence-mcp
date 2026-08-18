"""Real smoke test: faithfulness/grounding enforcement (Issue 5.1 acceptance criteria).

Requires Qdrant running with NVDA already ingested, and a real GEMINI_API_KEY in .env.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.analyze_filing import analyze_filing  # noqa: E402


async def main() -> None:
    result = await analyze_filing("What did NVIDIA say about their Mars operations?", "NVDA")

    print("Answer:", result["answer"])
    print("Confidence:", result["confidence"])

    answer_lower = result["answer"].lower()
    not_found_phrases = ["not present", "not found", "does not", "no information", "no mention"]
    assert any(p in answer_lower for p in not_found_phrases), (
        f"expected the model to say the info isn't in the filing, got: {result['answer']!r}"
    )

    print("OK: model correctly declined to answer instead of hallucinating")


if __name__ == "__main__":
    asyncio.run(main())
