# Evaluation Results

This directory holds the eval dataset (`questions.jsonl`) and measured results
(`results/`) for `evaluation/run_eval.py` -- an automated RAG quality check meant to run
before every release, not just once.

## Methodology

- **Dataset**: 50 question-answer pairs across 5 companies (AAPL, NVDA, MSFT, AMZN, GOOGL;
  10 questions each) and 5 question types (factual lookup, comparative, risk-related,
  forward-looking, specific metric; 2 each per company). Ground truth was extracted from
  each company's real, most recently ingested 10-K -- not LLM-invented -- and independently
  verified against the source filings (see the `eval/questions.jsonl` commit history for
  details of that verification pass).
- **Scoring**: each question is run through `analyze_filing`'s retrieve-then-generate
  pipeline, then scored by RAGAS on three metrics, using this project's own Gemini key
  as the judge (not RAGAS's OpenAI default):
  - `faithfulness` -- is the generated answer actually grounded in the retrieved context?
  - `answer_correctness` -- does the answer match the ground truth (factual + semantic
    similarity)?
  - `context_recall` -- did retrieval actually find the passages needed to answer?
- **Retrieval strategies compared**: the same 50 questions were run three times, varying
  only which retrieval function `analyze_filing` used, to measure what each stage of the
  retrieval pipeline (built across Epics 3-5) actually contributes.

## Results (measured 2026-08-24 to 2026-08-25, full 50-question runs)

| Retrieval strategy | Faithfulness | Correctness | Context Recall |
|---|---|---|---|
| v1: semantic-only (dense embeddings) | 0.92 | 0.67 | 0.84 |
| v2: hybrid (BM25 + semantic via RRF) -- **production default** | 0.95 | 0.78 | 0.99 |
| v3: hybrid + cross-encoder reranking | **0.98** | **0.82** | **1.00** |

Raw per-question scores and generated answers are in `results/v1_semantic.json`,
`results/v2_hybrid.json`, and `results/v3_hybrid_rerank.json`.

### Targets

| Metric | Target (v2) | v2 result | Met? |
|---|---|---|---|
| Faithfulness | >= 0.78 | 0.95 | Yes |
| Context Recall | >= 0.72 | 0.99 | Yes |

**Proposed CI minimum: Faithfulness >= 0.75.** All three retrieval strategies clear this,
so it's a real floor, not a rubber stamp -- a regression that dropped below it would
indicate something is actually broken (e.g. a bad prompt change, a retrieval bug), not just
normal variance.

### On the reranker

Epic 5's follow-up eval (a much smaller question set) found the cross-encoder reranker
could occasionally rank a less-relevant passage above a more-relevant one on dense SEC
filing text, and left it opt-in (`use_reranker=False` by default) pending a larger,
more decisive test. This 50-question run is that test: **the reranker outperforms plain
hybrid retrieval on every metric** (0.98 vs 0.95 faithfulness, 0.82 vs 0.78 correctness,
1.00 vs 0.99 context recall). The earlier concern doesn't reproduce at this sample size.

This is a real, measured reason to reconsider defaulting `use_reranker=True` -- not yet
acted on here, since changing a production default is a decision worth making
deliberately rather than as a side effect of writing up eval results.

## Running the eval

```bash
# Full run
python evaluation/run_eval.py --output eval/results/2026-09-01.json

# Compare retrieval strategies
python evaluation/run_eval.py --output eval/results/semantic.json --retrieval-mode semantic
python evaluation/run_eval.py --output eval/results/rerank.json --retrieval-mode hybrid_rerank

# In batches (useful for the Gemini free tier's daily request quota)
python evaluation/run_eval.py --output eval/results/batch1.json --offset 0 --limit 15
python evaluation/run_eval.py --output eval/results/batch2.json --offset 15 --limit 15
python evaluation/merge_results.py eval/results/batch1.json eval/results/batch2.json \
    --output eval/results/final.json
```

See `evaluation/run_eval.py`'s module docstring for the full batching workflow.
