"""Print an offline schema graph payload; Neo4j upload is a future feature."""

import argparse
import json
from pathlib import Path

from src.schema.build_graph import build_schema_graph


def main(argv: list[str] | None = None) -> int:
    """Inspect graph metadata without requiring a Neo4j installation or server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build_schema_graph(args.db), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
