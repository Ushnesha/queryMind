"""New offline baseline entry point for this initially empty repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.db import execute_sql, introspect_schema
from src.llm import get_provider


def run_baseline(question: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    """Generate and execute one demo query using the shared read-only components."""
    schema = introspect_schema(db_path)
    sql = get_provider().generate(question, schema)
    return {"question": question, "sql": sql, **execute_sql(sql, db_path=db_path)}


def main(argv: list[str] | None = None) -> int:
    """Run the offline baseline and optionally append one JSONL trace record."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Who are the top 3 customers by total spending?")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_baseline(args.question, db_path=args.db)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"{error}\n")
    if args.trace:
        from src.trace import write_jsonl

        write_jsonl(args.trace, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
