"""Smoke-test ablation switches: python -m scripts.run_ablation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation import run_ablation


def main() -> None:
    """Run one question under each starter toggle configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Who are the top 3 customers by total spending?")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = run_ablation(args.question, db_path=args.db_path)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
