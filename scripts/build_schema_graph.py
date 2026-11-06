"""Inspect SQLite schemas or explicitly upload selected schema metadata to Neo4j."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema.build_graph import build_schema_graph
from src.schema.neo4j_store import open_driver_from_env, upload_schema_graph


def main(argv: list[str] | None = None) -> int:
    """Default to offline inspection; --upload explicitly enables Neo4j writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--db", type=Path, help="Single SQLite database; defaults to configured demo database")
    source.add_argument("--spider-root", type=Path, help="Spider dataset root or its database/ directory")
    parser.add_argument("--db-id", action="append", default=[], help="Spider database ID; repeat to select several")
    parser.add_argument("--upload", action="store_true", help="Explicitly upload metadata to configured Neo4j")
    parser.add_argument("--output", type=Path, help="Also save the JSON payload to this file")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    if args.spider_root:
        if not args.db_id:
            parser.error("--spider-root requires explicit --db-id selections")
        root = args.spider_root.expanduser().resolve()
        database_root = root / "database" if (root / "database").is_dir() else root
        selected: list[tuple[Path | None, str | None]] = []
        for identifier in dict.fromkeys(args.db_id):
            if Path(identifier).name != identifier or identifier in {".", ".."}:
                parser.error("--db-id must be a database directory name")
            path = database_root / identifier / f"{identifier}.sqlite"
            if not path.is_file():
                parser.error(f"Spider SQLite database not found: {path}")
            selected.append((path, identifier))
    else:
        if len(args.db_id) > 1:
            parser.error("Use --spider-root to select multiple --db-id values")
        selected = [(args.db, args.db_id[0] if args.db_id else None)]
    if args.output and args.output.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        parser.error("--output must be a JSON artifact, not a SQLite database path")
    if args.output and any(path is not None and args.output.resolve() == path.resolve() for path, _ in selected):
        parser.error("--output cannot overwrite a source database")
    try:
        payloads = [build_schema_graph(path, database_id=identifier) for path, identifier in selected]
        if args.upload:
            with open_driver_from_env() as driver:
                for payload in payloads:
                    payload["upload"] = upload_schema_graph(payload, driver=driver)
                    payload["status"] = "uploaded"
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(2, f"{exc}\n")
    except Exception as exc:
        # Optional driver exceptions should not leak connection details or emit a traceback.
        parser.exit(2, f"Schema graph operation failed ({type(exc).__name__}); check the database and Neo4j configuration.\n")
    document = payloads[0] if len(payloads) == 1 else {
        "status": "uploaded" if args.upload else "offline_payloads_only", "schemas": payloads,
    }
    rendered = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
