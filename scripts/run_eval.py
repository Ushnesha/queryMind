"""Run the tiny offline reference-SQL fixture: python -m scripts.run_eval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation import load_questions, run_evaluation


def main() -> None:
    """Parse fixture/database/output locations and emit a JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = run_evaluation(load_questions(args.questions), db_path=args.db_path)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
