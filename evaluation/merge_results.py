"""Merges multiple run_eval.py batch JSON reports (from --offset/--limit runs) into one final
report with recomputed summary averages.

Usage:
    python evaluation/merge_results.py eval/results/batch1.json eval/results/batch2.json \
        --output eval/results/2026-08-20.json
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", nargs="+", help="Batch JSON files to merge, in any order")
    parser.add_argument("--output", required=True, help="Path to write the merged JSON report to")
    args = parser.parse_args()

    batch_reports = [json.loads(Path(p).read_text()) for p in args.batches]

    modes = {r["retrieval_mode"] for r in batch_reports}
    if len(modes) > 1:
        raise ValueError(f"Batches use different retrieval modes, refusing to merge: {modes}")

    per_question = [q for r in batch_reports for q in r["per_question"]]
    if not per_question:
        raise ValueError("No questions found across the given batch files")

    def avg(key: str) -> float:
        return sum(r[key] for r in per_question) / len(per_question)

    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "retrieval_mode": modes.pop(),
        "num_questions": len(per_question),
        "summary": {
            "faithfulness": avg("faithfulness"),
            "answer_correctness": avg("answer_correctness"),
            "context_recall": avg("context_recall"),
        },
        "per_question": per_question,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    s = report["summary"]
    print(f"Merged {len(per_question)} questions from {len(args.batches)} batch(es)")
    print(
        f"Faithfulness: {s['faithfulness']:.2f} | "
        f"Correctness: {s['answer_correctness']:.2f} | "
        f"Context Recall: {s['context_recall']:.2f}"
    )
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
