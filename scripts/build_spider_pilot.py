"""Build a seeded Spider 1.0 dev pilot in the stakeholder's question format.

Each Spider database gets one YAML file that the stakeholder's loader
(`external/agentic-sql-analyst/src/dataset.py`) accepts unchanged, so b0, b1 and
QueryMind are all scored by the stakeholder's own `score_record` rules.

Selection is a seeded uniform sample of dev.json indices. A sampled case is
dropped (and recorded in the manifest) when its gold SQL fails or returns no
rows under a read-only connection: an empty gold result is matched by any
query that returns nothing, which would inflate every arm equally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MULTI = re.compile(r"\bJOIN\b|\bINTERSECT\b|\bUNION\b|\bEXCEPT\b|\(\s*SELECT\b", re.IGNORECASE)


def complexity(sql: str) -> str:
    """Return 'multi' for joins, set operations or nesting, else 'single'."""
    return "multi" if MULTI.search(sql) else "single"


def gold_rows(db_path: Path, sql: str) -> int:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return len(conn.execute(sql.strip().rstrip(";")).fetchall())
    finally:
        conn.close()


def build(dataset_root: Path, out_dir: Path, size: int, seed: int) -> dict:
    dev_path = dataset_root / "dev.json"
    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    order = list(range(len(dev)))
    random.Random(seed).shuffle(order)

    kept: list[int] = []
    dropped: list[dict] = []
    for index in order:
        if len(kept) == size:
            break
        case = dev[index]
        db_path = dataset_root / "database" / case["db_id"] / f"{case['db_id']}.sqlite"
        try:
            rows = gold_rows(db_path, case["query"])
        except sqlite3.Error as exc:
            dropped.append({"index": index, "db_id": case["db_id"], "reason": f"gold SQL error: {exc}"})
            continue
        if rows == 0:
            dropped.append({"index": index, "db_id": case["db_id"], "reason": "gold result is empty"})
            continue
        kept.append(index)

    by_db: dict[str, list[dict]] = {}
    for index in sorted(kept):
        case = dev[index]
        sql = case["query"].strip().rstrip(";")
        by_db.setdefault(case["db_id"], []).append({
            "id": f"S{index:04d}",
            "set": complexity(sql),
            "kind": "reference",
            "ordered": bool(re.search(r"\bORDER\s+BY\b", sql, re.IGNORECASE)),
            "question": case["question"],
            "reference_sql": sql + "\n",
            "note": f"Spider 1.0 dev.json index {index}; db_id {case['db_id']}",
        })

    questions_dir = out_dir / "questions"
    questions_dir.mkdir(parents=True, exist_ok=True)
    for stale in questions_dir.glob("*.yaml"):
        stale.unlink()
    for db_id, items in sorted(by_db.items()):
        (questions_dir / f"{db_id}.yaml").write_text(
            yaml.safe_dump(items, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
        )

    manifest = {
        "source": "Spider 1.0 dev split (dev.json), Yu et al. 2018, CC BY-SA 4.0",
        "dev_json_sha256": hashlib.sha256(dev_path.read_bytes()).hexdigest(),
        "source_questions": len(dev),
        "seed": seed,
        "requested": size,
        "selected": len(kept),
        "databases": {db_id: [item["id"] for item in items] for db_id, items in sorted(by_db.items())},
        "by_complexity": {
            label: sum(1 for items in by_db.values() for item in items if item["set"] == label)
            for label in ("single", "multi")
        },
        "ordered_cases": sum(1 for items in by_db.values() for item in items if item["ordered"]),
        "dropped": dropped,
        "complexity_rule": "multi = gold SQL contains JOIN, INTERSECT, UNION, EXCEPT or a nested SELECT",
        "ordered_rule": "row order enforced when gold SQL contains ORDER BY",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=PROJECT_ROOT / "data/spider_data")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/spider_pilot")
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=598)
    args = parser.parse_args(argv)
    manifest = build(args.dataset_root, args.out, args.size, args.seed)
    print(json.dumps({k: manifest[k] for k in ("selected", "by_complexity", "ordered_cases")}))
    print(f"databases: {len(manifest['databases'])}, dropped: {len(manifest['dropped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
