"""MCP tool: answer a question about a filing using RAG, grounded with citations."""

from pathlib import Path

import anyio

from llm import generate
from retrieval.hybrid import hybrid_search as _search
from retrieval.rerank import rerank as _rerank

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "analyze_filing.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

TOP_K = 5
RERANK_CANDIDATE_POOL = 10

# Thresholds are calibrated against this project's own retrieval scores: relevant e5 passages
# scored ~0.85-0.87 and irrelevant ones ~0.67-0.7 in testing (see Issue 3.2/3.4), so 0.8/0.65
# separate "clearly relevant" from "borderline" from "weak match" with margin either side.
# Note: hybrid_search's top result can occasionally be a BM25-only match with score=0.0 (no
# cosine score to report -- see hybrid.py), which this reads as "low confidence" even if the
# match is actually strong; a known, minor imprecision rather than a wrong result.
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


def _run_analysis(
    question: str,
    ticker: str,
    form_type: str | None,
    fiscal_year: int | None,
    use_reranker: bool,
    search_fn=None,
) -> dict:
    """Core retrieve-then-generate logic, with the retrieval function swappable.

    Exists (rather than hardcoding hybrid_search) so evaluation/run_eval.py can compare
    retrieval strategies (e.g. semantic-only vs hybrid) using the exact same downstream
    generation/confidence logic as the production tool -- see Issue 7.3.
    """
    search_fn = search_fn or _search
    pool_size = RERANK_CANDIDATE_POOL if use_reranker else TOP_K
    results = search_fn(
        question, ticker=ticker, form_type=form_type, fiscal_year=fiscal_year, top_k=pool_size
    )
    if use_reranker and results:
        results = _rerank(question, results, top_k=TOP_K)

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
    use_reranker: bool = False,
) -> dict:
    """Answer a question about a company's SEC filing with citations to the source document.

    Uses retrieval-augmented generation — every claim is grounded in the actual filing text.

    Args:
        question: Specific question about the filing
        ticker: Company ticker
        form_type: '10-K' or '10-Q'
        fiscal_year: Specific year (defaults to most recent)
        use_reranker: If True, retrieves a wider candidate pool and re-scores it with a
            cross-encoder before answering. Off by default -- testing (Issue 5.3) found the
            specified cross-encoder model can occasionally rank a less-relevant passage above
            a more-relevant one on dense SEC-filing text, so this is opt-in pending further
            evaluation or a domain-tuned model, not a default-on production behavior.

    Returns:
        answer: Generated answer grounded in the filing
        sources: List of passages cited, each with section name, page number, and text excerpt
        confidence: 'high' / 'medium' / 'low' based on retrieval score distribution
    """
    # Runs off the event loop thread -- see search_filings.py for why.
    return await anyio.to_thread.run_sync(
        _run_analysis, question, ticker, form_type, fiscal_year, use_reranker
    )
