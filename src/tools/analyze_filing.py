"""MCP tool: answer a question about a filing using RAG, grounded with citations."""

import threading
import time
from pathlib import Path

import anyio
from langfuse import get_client, observe

from config import GEMINI_MODEL
from llm import generate_with_usage
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


def _score_faithfulness_background(trace_id: str, question: str, answer: str, contexts: list[str]):
    """Scores the trace's faithfulness with RAGAS in a background thread, after the tool has
    already returned its answer -- so it doesn't add RAGAS's ~2 extra LLM calls to the
    latency the user waits on (Issue 8.3's 8s target), and doesn't consume Gemini quota on
    the request's critical path. Best-effort: a scoring failure must never surface to the
    caller, since the real answer was already returned successfully.
    """
    try:
        import asyncio

        from ragas.dataset_schema import SingleTurnSample
        from ragas.metrics import Faithfulness

        from ragas_judge import get_judge_llm

        sample = SingleTurnSample(
            user_input=question, response=answer, retrieved_contexts=contexts or ["(none)"]
        )
        score = asyncio.run(Faithfulness(llm=get_judge_llm()).single_turn_ascore(sample))
        get_client().create_score(
            trace_id=trace_id, name="faithfulness", value=score, data_type="NUMERIC"
        )
    except Exception:
        pass


@observe(name="retrieval", as_type="retriever")
def _retrieve(
    question: str,
    ticker: str,
    form_type: str | None,
    fiscal_year: int | None,
    use_reranker: bool,
    search_fn,
) -> list:
    start = time.perf_counter()
    pool_size = RERANK_CANDIDATE_POOL if use_reranker else TOP_K
    results = search_fn(
        question, ticker=ticker, form_type=form_type, fiscal_year=fiscal_year, top_k=pool_size
    )
    if use_reranker and results:
        results = _rerank(question, results, top_k=TOP_K)
    latency_ms = round((time.perf_counter() - start) * 1000)

    get_client().update_current_span(
        input={
            "query": question,
            "ticker": ticker,
            "form_type": form_type,
            "fiscal_year": fiscal_year,
            "use_reranker": use_reranker,
        },
        output=[
            {
                "section_name": r.section_name,
                "page_number": r.page_number,
                "score": r.score,
                "preview": r.text[:150],
            }
            for r in results
        ],
        metadata={"retrieval_latency_ms": latency_ms},
    )
    return results


@observe(name="llm_call", as_type="generation")
def _generate(question: str, context: str) -> str:
    prompt = _PROMPT_TEMPLATE.format(question=question, context=context)
    start = time.perf_counter()
    answer, usage_details = generate_with_usage(prompt)
    latency_ms = round((time.perf_counter() - start) * 1000)

    get_client().update_current_generation(
        input=prompt,
        output=answer,
        model=GEMINI_MODEL,
        usage_details=usage_details or None,
        metadata={"llm_call_latency_ms": latency_ms},
    )
    return answer


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
    results = _retrieve(question, ticker, form_type, fiscal_year, use_reranker, search_fn)

    if not results:
        return {
            "answer": (
                f"No indexed filing content found for {ticker} {form_type}. "
                "Call ingest_company_filings first."
            ),
            "sources": [],
            "confidence": "low",
        }

    answer = _generate(question, _format_context(results))

    trace_id = get_client().get_current_trace_id()
    if trace_id:
        threading.Thread(
            target=_score_faithfulness_background,
            args=(trace_id, question, answer, [r.text for r in results]),
            daemon=True,
        ).start()

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


@observe(name="analyze_filing")
async def analyze_filing(
    question: str,
    ticker: str,
    form_type: str = "10-K",
    fiscal_year: int | None = None,
    use_reranker: bool = False,
) -> dict:
    """Answer a question about a company's SEC filing with citations to the source document.

    Use this instead of web search or general/prior knowledge whenever the question could be
    answered from a company's own 10-K or 10-Q -- the answer is grounded in the actual filing
    text with citations, not paraphrased from memory or an external source.

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
    start = time.perf_counter()
    # Runs off the event loop thread -- see search_filings.py for why.
    result = await anyio.to_thread.run_sync(
        _run_analysis, question, ticker, form_type, fiscal_year, use_reranker
    )
    total_latency_ms = round((time.perf_counter() - start) * 1000)
    get_client().update_current_span(metadata={"total_latency_ms": total_latency_ms})
    return result
