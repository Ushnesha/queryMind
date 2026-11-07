"""Optimizer-only benchmark on Spider dev gold SQL. PRELIMINARY: small subset, not a final study.

Copies the largest dev databases to a temp dir (the shared files are never touched), runs
optimize_sql on each gold query once, times original vs rewrite, and saves results to
eval/results/. --index-fks adds indexes on foreign-key columns of the copies (disclosed in
the output) so plans have something to improve.
"""

import argparse
import json
import math
import shutil
import statistics
import sys
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from src.db import connect_readonly, introspect_schema
from src.optimizer import optimize_sql
from src.optimizer.equality import compare_results, has_top_level_order_by, run_limited
from src.optimizer.explain import plan_improved

ROOT = Path(__file__).resolve().parents[1]
WARMUPS, RUNS = 1, 5
TIME_LIMIT_S = 30.0  # per execution during timing


def pick_queries(spider: Path, n_dbs: int, limit: int) -> list[dict]:
    """Take gold queries evenly from the n_dbs largest dev databases."""
    dev = json.loads((spider / "dev.json").read_text(encoding="utf-8"))
    ids = sorted({d["db_id"] for d in dev})
    size = lambda i: (spider / "database" / i / f"{i}.sqlite").stat().st_size
    largest = sorted(ids, key=size, reverse=True)[:n_dbs]
    per_db = math.ceil(limit / len(largest))
    picked = []
    for db_id in largest:
        picked += [d for d in dev if d["db_id"] == db_id][:per_db]
    return picked[:limit]


def prepare_copy(spider: Path, db_id: str, workdir: Path, index_fks: bool) -> tuple[Path, int]:
    """Copy one database; optionally index its foreign-key columns. Returns (path, indexes)."""
    source = spider / "database" / db_id / f"{db_id}.sqlite"
    copy = workdir / f"{db_id}.sqlite"
    shutil.copy(source, copy)
    made = 0
    if index_fks:
        import sqlite3

        with closing(sqlite3.connect(copy)) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
                    conn.execute(f'CREATE INDEX IF NOT EXISTS "bx_{t}_{fk[3]}" ON "{t}"("{fk[3]}")')
                    made += 1
            conn.commit()
    return copy, made


def time_query(sql: str, db: Path) -> tuple[float | None, list, list]:
    """Median ms over WARMUPS+RUNS runs, plus rows and columns. None ms on error/timeout."""
    try:
        times = []
        for i in range(WARMUPS + RUNS):
            start = perf_counter()
            rows, cols = run_limited(sql, db, TIME_LIMIT_S)
            if i >= WARMUPS:
                times.append((perf_counter() - start) * 1000)
        return statistics.median(times), rows, cols
    except Exception:
        return None, [], []


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spider", type=Path, default=ROOT / "data" / "spider_data")
    parser.add_argument("--dbs", type=int, default=3, help="how many of the largest dev DBs")
    parser.add_argument("--limit", type=int, default=30, help="total queries")
    parser.add_argument("--index-fks", action="store_true", help="index FK columns on the copies")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")

    queries = pick_queries(args.spider, args.dbs, args.limit)
    rows_out, index_counts = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        copies = {}
        for q in queries:
            if q["db_id"] not in copies:
                copies[q["db_id"]], index_counts[q["db_id"]] = prepare_copy(
                    args.spider, q["db_id"], Path(tmp), args.index_fks)
        schemas = {i: introspect_schema(p) for i, p in copies.items()}
        for n, q in enumerate(queries, 1):
            db, sql = copies[q["db_id"]], q["query"]
            opt = optimize_sql(sql, q["question"], schemas[q["db_id"]], db_path=db)
            row = {"db_id": q["db_id"], "question": q["question"], "original_sql": sql,
                   "changed": opt["changed"], "reason": opt["reason"], "llm_calls": opt["llm_calls"],
                   "optimizer_ms": opt["latency_ms"], "optimized_sql": opt["optimized_sql"]}
            if opt["changed"]:
                before_ms, r_a, c_a = time_query(sql, db)
                after_ms, r_b, c_b = time_query(opt["sql"], db)
                row.update(
                    before_ms=before_ms, after_ms=after_ms,
                    plan_improved=plan_improved(opt["plan_before"], opt["plan_after"]),
                    # independent re-check of the gate, on the rows we just timed
                    equal=before_ms is not None and after_ms is not None and compare_results(
                        r_a, c_a, r_b, c_b, ordered=has_top_level_order_by(sql)),
                )
            rows_out.append(row)
            print(f"[{n}/{len(queries)}] {q['db_id']}: {'REWRITTEN' if row['changed'] else 'kept'}")

    rewritten = [r for r in rows_out if r["changed"]]
    timed = [r for r in rewritten if r["before_ms"] is not None and r["after_ms"] is not None]
    summary = {
        "label": "PRELIMINARY: optimizer-only, Spider dev gold SQL, small subset",
        "index_fks_on_copies": args.index_fks, "indexes_added": index_counts,
        "databases": sorted(index_counts), "queries_considered": len(rows_out),
        "queries_rewritten": len(rewritten),
        "equality_maintained": f"{sum(r['equal'] for r in rewritten)}/{len(rewritten)}",
        "plan_improved": f"{sum(r['plan_improved'] for r in rewritten)}/{len(rewritten)}",
        "median_ms_before_rewritten": median([r["before_ms"] for r in timed]),
        "median_ms_after_rewritten": median([r["after_ms"] for r in timed]),
        "llm_calls": sum(r["llm_calls"] for r in rows_out),
        "timing": f"{WARMUPS} warm-up + {RUNS} runs, median; time limit {TIME_LIMIT_S}s",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "indexed" if args.index_fks else "asis"
    base = args.out / f"optimizer_benchmark_{tag}_{stamp}"
    base.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "queries": rows_out}, indent=2), encoding="utf-8")
    table = "\n".join(f"| {k} | {v} |" for k, v in summary.items()
                      if k in ("queries_considered", "queries_rewritten", "equality_maintained",
                               "plan_improved", "median_ms_before_rewritten",
                               "median_ms_after_rewritten", "llm_calls"))
    base.with_suffix(".md").write_text(
        f"# Optimizer benchmark ({summary['label']})\n\n"
        f"Databases: {', '.join(summary['databases'])}. FK indexes added to copies: "
        f"{args.index_fks}. {summary['timing']}.\n\n| Metric | Value |\n| --- | --- |\n{table}\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("saved:", base.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
