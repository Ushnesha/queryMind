"""Inspect the starter optimizer; this is not a completed optimization study."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import execute_sql, introspect_schema
from src.optimizer import compare_results, optimize_sql


def main(argv: list[str] | None = None) -> int:
    """Report unchanged SQL plans, measured execution times and result equality."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite database path (default: settings).")
    parser.add_argument("--sql", default="SELECT COUNT(*) AS customer_count FROM customers")
    parser.add_argument("--question", default="How many customers are there?")
    args = parser.parse_args(argv)
    try:
        schema = introspect_schema(args.db)
        candidate = optimize_sql(args.sql, args.question, schema, db_path=args.db)
        before = execute_sql(args.sql, db_path=args.db)
        after = execute_sql(candidate["sql"], db_path=args.db)
        output = {
            "status": "starter_no_rewrite",
            "optimization": candidate,
            "execution_time_before_ms": before["execution_time_ms"],
            "execution_time_after_ms": after["execution_time_ms"],
            "results_equal": compare_results(
                before["rows"], before["columns"], after["rows"], after["columns"]
            ),
        }
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Benchmark failed: {exc}\n")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
