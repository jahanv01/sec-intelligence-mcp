"""Runs the Epic 7 evaluation dataset (eval/questions.jsonl) through analyze_filing's RAG
pipeline and scores each answer with RAGAS (faithfulness, answer_correctness, context_recall).

Usage:
    python evaluation/run_eval.py --output eval/results/2026-08-20.json
    python evaluation/run_eval.py --output eval/results/v1_semantic.json --retrieval-mode semantic
    python evaluation/run_eval.py --output eval/results/smoke.json --limit 5

Running in batches (e.g. to spread a run across the free-tier rate limit over multiple
sessions) -- each batch writes its own file, then merge_results.py combines them:
    python evaluation/run_eval.py --output eval/results/batch1.json --offset 0 --limit 20
    python evaluation/run_eval.py --output eval/results/batch2.json --offset 20 --limit 20
    python evaluation/run_eval.py --output eval/results/batch3.json --offset 40
    python evaluation/merge_results.py eval/results/batch1.json eval/results/batch2.json \
        eval/results/batch3.json --output eval/results/2026-08-20.json
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.metrics import AnswerCorrectness, Faithfulness, LLMContextRecall  # noqa: E402
from ragas.metrics._answer_similarity import AnswerSimilarity  # noqa: E402

from ragas_judge import get_judge_embeddings, get_judge_llm  # noqa: E402
from retrieval.hybrid import hybrid_search  # noqa: E402
from retrieval.search import search as semantic_search  # noqa: E402
from tools.analyze_filing import _run_analysis  # noqa: E402

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "eval" / "questions.jsonl"

RETRIEVAL_MODES = {
    "semantic": {"search_fn": semantic_search, "use_reranker": False},
    "hybrid": {"search_fn": hybrid_search, "use_reranker": False},
    "hybrid_rerank": {"search_fn": hybrid_search, "use_reranker": True},
}


def _load_questions(offset: int, limit: int | None) -> list[dict]:
    questions = [json.loads(line) for line in QUESTIONS_PATH.read_text().splitlines() if line]
    questions = questions[offset:]
    return questions[:limit] if limit else questions


async def _score_question(q: dict, mode: dict, metrics: dict) -> dict:
    result = _run_analysis(
        question=q["question"],
        ticker=q["ticker"],
        form_type=q.get("form_type", "10-K"),
        fiscal_year=q.get("fiscal_year"),
        use_reranker=mode["use_reranker"],
        search_fn=mode["search_fn"],
    )
    retrieved_contexts = [s["text"] for s in result["sources"]] or ["(no context retrieved)"]

    sample = SingleTurnSample(
        user_input=q["question"],
        response=result["answer"],
        retrieved_contexts=retrieved_contexts,
        reference=q["ground_truth"],
    )

    faithfulness = await metrics["faithfulness"].single_turn_ascore(sample)
    correctness = await metrics["answer_correctness"].single_turn_ascore(sample)
    context_recall = await metrics["context_recall"].single_turn_ascore(sample)

    return {
        "ticker": q["ticker"],
        "question": q["question"],
        "answer": result["answer"],
        "faithfulness": faithfulness,
        "answer_correctness": correctness,
        "context_recall": context_recall,
    }


def _build_report(mode_name: str, per_question: list[dict]) -> dict:
    def avg(key: str) -> float:
        return sum(r[key] for r in per_question) / len(per_question)

    summary = {
        "faithfulness": avg("faithfulness"),
        "answer_correctness": avg("answer_correctness"),
        "context_recall": avg("context_recall"),
    }

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "retrieval_mode": mode_name,
        "num_questions": len(per_question),
        "summary": summary,
        "per_question": per_question,
    }


async def _run(mode_name: str, offset: int, limit: int | None, output_path: Path) -> dict:
    questions = _load_questions(offset, limit)
    mode = RETRIEVAL_MODES[mode_name]
    llm = get_judge_llm()
    embeddings = get_judge_embeddings()
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_correctness": AnswerCorrectness(
            llm=llm,
            embeddings=embeddings,
            answer_similarity=AnswerSimilarity(embeddings=embeddings),
        ),
        "context_recall": LLMContextRecall(llm=llm),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    per_question = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['ticker']}: {q['question'][:60]}...", flush=True)
        per_question.append(await _score_question(q, mode, metrics))
        # Write after every question, not just at the end -- a batch that dies partway through
        # (rate limits, network blips) still leaves usable partial results on disk.
        output_path.write_text(json.dumps(_build_report(mode_name, per_question), indent=2))

    return _build_report(mode_name, per_question)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path to write the JSON report to")
    parser.add_argument(
        "--retrieval-mode",
        default="hybrid",
        choices=sorted(RETRIEVAL_MODES),
        help="Which retrieval strategy analyze_filing should use for this run",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only run N questions starting at --offset"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="Skip the first N questions (for running in batches)"
    )
    parser.add_argument(
        "--min-faithfulness",
        type=float,
        default=None,
        help="Exit non-zero if average faithfulness falls below this (for CI's eval-gate job)",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    report = asyncio.run(_run(args.retrieval_mode, args.offset, args.limit, output_path))

    s = report["summary"]
    print(
        f"\nFaithfulness: {s['faithfulness']:.2f} | "
        f"Correctness: {s['answer_correctness']:.2f} | "
        f"Context Recall: {s['context_recall']:.2f}"
    )
    print(f"Report written to {output_path}")

    if args.min_faithfulness is not None and s["faithfulness"] < args.min_faithfulness:
        print(
            f"FAIL: faithfulness {s['faithfulness']:.2f} is below the "
            f"required minimum {args.min_faithfulness:.2f}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
