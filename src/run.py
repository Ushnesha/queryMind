"""Offline starter CLI: python -m src.run --question '...'"""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.config import PROJECT_ROOT
from src.orchestrator import run_querymind
from src.trace import write_jsonl


def main(argv: list[str] | None = None) -> int:
    """Run a mock-provider query, optionally appending the complete JSONL trace."""
    parser = argparse.ArgumentParser(description="QueryMind offline Milestone 2 starter")
    parser.add_argument("--question", required=True)
    parser.add_argument("--schema-mode", choices=("flat", "neo4j"), default="flat")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--disable-syntax", action="store_true")
    parser.add_argument("--disable-semantic", action="store_true")
    parser.add_argument("--disable-optimizer", action="store_true")
    parser.add_argument("--disable-result-verifier", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    state = run_querymind(
        args.question, schema_mode=args.schema_mode, db_path=args.db_path,
        enable_syntax=not args.disable_syntax, enable_semantic=not args.disable_semantic,
        enable_optimizer=not args.disable_optimizer, enable_result_verifier=not args.disable_result_verifier,
    )
    print(json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False))
    if args.trace:
        write_jsonl(args.trace, state)
    return 1 if state["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
