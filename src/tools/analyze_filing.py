"""MCP tool: answer a question about a filing using RAG, grounded with citations."""

from pathlib import Path

import anyio

from llm import generate
from retrieval.search import search as _search

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "analyze_filing.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

TOP_K = 5

# Thresholds are calibrated against this project's own retrieval scores: relevant e5 passages
# scored ~0.85-0.87 and irrelevant ones ~0.67-0.7 in testing (see Issue 3.2/3.4), so 0.8/0.65
# separate "clearly relevant" from "borderline" from "weak match" with margin either side.
_HIGH_CONFIDENCE_THRESHOLD = 0.8
_MEDIUM_CONFIDENCE_THRESHOLD = 0.65


def _confidence(top_score: float) -> str:
    if top_score >= _HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if top_score >= _MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _format_context(results: list) -> str:
    blocks = []
    for r in results:
        page = f", Page: {r.page_number}" if r.page_number else ""
        blocks.append(f"[Section: {r.section_name}{page}]\n{r.text}")
    return "\n\n".join(blocks)


def _analyze_filing_sync(
    question: str,
    ticker: str,
    form_type: str | None,
    fiscal_year: int | None,
) -> dict:
    results = _search(
        question, ticker=ticker, form_type=form_type, fiscal_year=fiscal_year, top_k=TOP_K
    )

    if not results:
        return {
            "answer": (
                f"No indexed filing content found for {ticker} {form_type}. "
                "Call ingest_company_filings first."
            ),
            "sources": [],
            "confidence": "low",
        }

    prompt = _PROMPT_TEMPLATE.format(question=question, context=_format_context(results))
    answer = generate(prompt)

    return {
        "answer": answer,
        "sources": [
            {
                "section_name": r.section_name,
                "page_number": r.page_number,
                "text": r.text,
            }
            for r in results
        ],
        "confidence": _confidence(results[0].score),
    }


async def analyze_filing(
    question: str,
    ticker: str,
    form_type: str = "10-K",
    fiscal_year: int | None = None,
) -> dict:
    """Answer a question about a company's SEC filing with citations to the source document.

    Uses retrieval-augmented generation — every claim is grounded in the actual filing text.

    Args:
        question: Specific question about the filing
        ticker: Company ticker
        form_type: '10-K' or '10-Q'
        fiscal_year: Specific year (defaults to most recent)

    Returns:
        answer: Generated answer grounded in the filing
        sources: List of passages cited, each with section name, page number, and text excerpt
        confidence: 'high' / 'medium' / 'low' based on retrieval score distribution
    """
    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(
        _analyze_filing_sync, question, ticker, form_type, fiscal_year
    )
