"""Run the paired node ablation experiment: python -m scripts.run_ablation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_eval import render_report, select_questions, write_artifacts
from src.config import PROJECT_ROOT
from src.evaluation import load_questions, run_ablation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=PROJECT_ROOT / "eval/milestone2.yaml")
    parser.add_argument("--question", help="Run a single-question switch smoke check instead of the experiment")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--include-syntax", action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "eval/results/ablation.json")
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        questions = args.question if args.question is not None else select_questions(load_questions(args.questions), "ablation", args.limit)
        report = run_ablation(questions, db_path=args.db_path, include_syntax=args.include_syntax)
        write_artifacts(report, args.output, jsonl=args.jsonl, markdown=args.markdown)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(render_report(report))
    print(f"Saved report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
