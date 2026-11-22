"""QueryMind optimizer benchmark suite.

Supports two evaluation modes:
1. --mode dual (default): Evaluates optimizer rewrites against both the original
   small stakeholder database (data/analytics.db) and the R5.1 large synthetic
   database (data/large_analytics.db) with interleaved timing, tri-state equality
   verification, and separate tracking of optimizer acceptance vs dual-db certification.
2. --mode spider: Legacy Spider dev gold query benchmarking across temporary copies.
"""

import argparse
import json
import math
import re
import shutil
import statistics
import sys
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
import yaml

from src.db import connect_readonly, introspect_schema
from src.optimizer import optimize_sql
from src.optimizer.equality import compare_results, has_top_level_order_by, run_limited
from src.optimizer.explain import explain_query_plan, plan_improved

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WARMUPS = 1
DEFAULT_RUNS = 5
DEFAULT_TIMEOUT_S = 30.0


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def compute_speedup(
    before_ms: float | None,
    after_ms: float | None,
    is_timeout_orig: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> float | None:
    """Calculate speedup ratio. Returns None if timings are unavailable."""
    if is_timeout_orig and after_ms is not None and after_ms > 0:
        return round((timeout_s * 1000.0) / after_ms, 3)
    if before_ms is not None and after_ms is not None and after_ms > 0:
        return round(before_ms / after_ms, 3)
    return None


def categorize_rejection(reason: str) -> str:
    """Group non-accepted query reasons into standard categories."""
    r = reason.lower()
    if "plan already reasonable" in r:
        return "already_optimal_skipped"
    if "distinct" in r:
        return "distinct_guard_rejected"
    if "results differ" in r:
        return "equality_gate_rejected"
    if "plan not improved" in r:
        return "plan_unimproved_rejected"
    if "timed out" in r or "timeout" in r:
        return "timeout_rejected"
    return "other_rejected"


def time_query_interleaved(
    orig_sql: str,
    opt_sql: str | None,
    db_path: Path | str,
    warmups: int = DEFAULT_WARMUPS,
    runs: int = DEFAULT_RUNS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Execute original and candidate SQL in interleaved fashion.

    Collects warmup + measured runs using perf_counter().
    Returns median timings, raw samples, tri-state equality (True, False, None),
    and per-query execution status.
    """
    has_candidate = opt_sql is not None and opt_sql.strip() != orig_sql.strip()
    orig_times: list[float] = []
    opt_times: list[float] = []
    orig_rows: list[list[Any]] | None = None
    orig_cols: list[str] | None = None
    opt_rows: list[list[Any]] | None = None
    opt_cols: list[str] | None = None

    status_orig = "ok"
    status_opt = "ok"
    orig_aborted = False
    opt_aborted = False

    total_iters = warmups + runs
    for i in range(total_iters):
        # 1. Original query
        if not orig_aborted:
            try:
                t0 = perf_counter()
                rows, cols = run_limited(orig_sql, db_path, timeout_s)
                dt_ms = (perf_counter() - t0) * 1000.0
                if orig_rows is None:
                    orig_rows, orig_cols = rows, cols
                if i >= warmups:
                    orig_times.append(dt_ms)
            except Exception as exc:
                orig_aborted = True
                status_orig = (
                    f"timeout (> {timeout_s}s)"
                    if "interrupted" in str(exc).lower()
                    else f"error: {exc}"
                )

        # 2. Candidate query (interleaved)
        if has_candidate and not opt_aborted:
            try:
                t0 = perf_counter()
                rows, cols = run_limited(opt_sql, db_path, timeout_s)
                dt_ms = (perf_counter() - t0) * 1000.0
                if opt_rows is None:
                    opt_rows, opt_cols = rows, cols
                if i >= warmups:
                    opt_times.append(dt_ms)
            except Exception as exc:
                opt_aborted = True
                status_opt = (
                    f"timeout (> {timeout_s}s)"
                    if "interrupted" in str(exc).lower()
                    else f"error: {exc}"
                )

    orig_median = round(statistics.median(orig_times), 3) if orig_times else None
    opt_median = round(statistics.median(opt_times), 3) if opt_times else None

    # Determine equality (tri-state: True, False, None)
    if not has_candidate:
        eq_val: bool | None = True
    elif status_orig != "ok" or status_opt != "ok" or orig_rows is None or opt_rows is None:
        eq_val = None
    else:
        try:
            eq_val = compare_results(
                orig_rows,
                orig_cols or [],
                opt_rows,
                opt_cols or [],
                ordered=has_top_level_order_by(orig_sql),
            )
        except Exception:
            eq_val = False

    is_timeout_orig = "timeout" in status_orig
    speedup = compute_speedup(orig_median, opt_median, is_timeout_orig, timeout_s)

    return {
        "before_ms": orig_median,
        "after_ms": opt_median,
        "raw_orig_ms": [round(t, 3) for t in orig_times],
        "raw_opt_ms": [round(t, 3) for t in opt_times],
        "speedup": speedup if has_candidate else 1.0,
        "results_equal": eq_val,
        "status_orig": status_orig,
        "status_opt": status_opt,
    }


def load_query_cases(path: Path) -> list[dict[str, Any]]:
    """Load query test cases from YAML or JSON file."""
    content = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    if isinstance(data, dict):
        if "cases" in data:
            return data["cases"]
        if "questions" in data:
            return data["questions"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unable to parse test cases from {path}")


def load_trace_cases(path: Path) -> list[dict[str, Any]]:
    """Extract benchmark query cases from a QueryMind JSONL trace file.

    Supports both stakeholder-mapped flat trace records and raw AgentState records.
    Filters out refused or execution-failed queries.
    """
    cases: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines, 1):
        if not line.strip():
            continue
        data = json.loads(line)
        state = data.get("state") if isinstance(data.get("state"), dict) else data

        # Filter out refused or failed queries
        if data.get("refused") is True or state.get("status") == "refused":
            continue
        if data.get("exec_ok") is False or state.get("status") == "error":
            continue

        qid = str(data.get("question_id") or state.get("question_id") or state.get("id") or f"T{idx:03d}")
        question = str(data.get("question") or state.get("question") or "")
        orig_sql = data.get("qm_original_sql") or state.get("original_sql") or ""
        applied = bool(data.get("qm_optimization_applied") or state.get("optimization_applied"))
        final_sql = data.get("sql") or state.get("sql") or ""
        opt_sql = state.get("optimized_sql") or (final_sql if applied else "")

        if orig_sql and orig_sql.strip():
            query = orig_sql.strip()
            cand = (
                final_sql.strip()
                if (applied and final_sql.strip() != orig_sql.strip())
                else (opt_sql.strip() if (opt_sql and opt_sql.strip() != orig_sql.strip()) else None)
            )
        else:
            query = final_sql.strip()
            cand = None

        if not query or query.startswith("NOT_ANSWERABLE"):
            continue

        category = str(data.get("category") or data.get("difficulty") or "frozen_system_trace")
        reason = str(data.get("qm_reason") or "Replay candidate from system trace")

        cases.append({
            "id": qid,
            "category": category,
            "question": question,
            "query": query,
            "candidate_rewrite": cand,
            "rewrite_reason": reason,
        })
    return cases


def run_dual_benchmark(args: argparse.Namespace) -> int:
    """Execute controlled dual-database benchmark across small and large databases."""
    small_db = Path(args.small_db)
    large_db = Path(args.large_db)

    if not small_db.exists():
        print(f"Error: small database not found at {small_db}", file=sys.stderr)
        return 1
    if not large_db.exists():
        print(f"Error: large database not found at {large_db}", file=sys.stderr)
        return 1

    if getattr(args, "traces", None):
        cases = load_trace_cases(Path(args.traces))
        suite_label = f"FROZEN_SYSTEM_TRACES: {Path(args.traces).name}"
        artifact_prefix = "optimizer_freeze_benchmark"
    else:
        cases = load_query_cases(Path(args.queries))
        suite_label = "CONTROLLED_DEVELOPMENT_SUITE: R5.3 scenario validation suite (not the frozen live system evaluation)"
        artifact_prefix = "optimizer_dual_benchmark"

    candidates_map: dict[str, str] = {}
    if args.candidates:
        cand_path = Path(args.candidates)
        cand_data = json.loads(cand_path.read_text(encoding="utf-8"))
        if isinstance(cand_data, dict):
            candidates_map = cand_data
        elif isinstance(cand_data, list):
            candidates_map = {item["id"]: item["candidate_rewrite"] for item in cand_data if "id" in item}

    # Evaluate optimizer proposals against the scale database schema & data
    large_schema = introspect_schema(large_db)

    records: list[dict[str, Any]] = []
    print(f"Starting dual-database benchmark on {len(cases)} queries...")
    print(f"Small DB: {small_db}")
    print(f"Large DB: {large_db}")
    print(f"Timing protocol: {args.warmups} warmup + {args.runs} runs (interleaved)")
    print("-" * 70)

    for n, item in enumerate(cases, 1):
        q_id = str(item.get("id", f"OPT{n:02d}"))
        category = str(item.get("category", "general"))
        question = item.get("question", "")
        sql = item.get("query") or item.get("sql", "")
        cand_sql = candidates_map.get(q_id) or item.get("candidate_rewrite")

        # LLM candidate generator
        if cand_sql:
            rewrite_reason = item.get("rewrite_reason", "Pre-determined candidate rewrite")
            llm_fn = lambda prompt, c=cand_sql, r=rewrite_reason: json.dumps({"sql": c, "reason": r})
        else:
            llm_fn = None

        opt = optimize_sql(
            sql,
            question,
            large_schema,
            db_path=large_db,
            llm=llm_fn,
            timeout_s=args.timeout,
        )

        optimizer_accepted = bool(opt["changed"])
        opt_sql = opt["optimized_sql"] if optimizer_accepted else None

        # Inspect plans on both databases
        plan_before_small = explain_query_plan(sql, db_path=small_db)
        plan_after_small = explain_query_plan(opt_sql or sql, db_path=small_db)
        plan_improved_small = (
            plan_improved(plan_before_small, plan_after_small) if optimizer_accepted else False
        )

        plan_before_large = explain_query_plan(sql, db_path=large_db)
        plan_after_large = explain_query_plan(opt_sql or sql, db_path=large_db)
        plan_improved_large = (
            plan_improved(plan_before_large, plan_after_large) if optimizer_accepted else False
        )

        # Time original and candidate on both databases
        small_timing = time_query_interleaved(
            sql, opt_sql, small_db, warmups=args.warmups, runs=args.runs, timeout_s=args.timeout
        )
        large_timing = time_query_interleaved(
            sql, opt_sql, large_db, warmups=args.warmups, runs=args.runs, timeout_s=args.timeout
        )

        small_eq = small_timing["results_equal"]
        large_eq = large_timing["results_equal"]

        # Strict dual-database report certification requirement
        report_certified = bool(
            optimizer_accepted and (small_eq is True) and (large_eq is True)
        )

        speedup_small = small_timing["speedup"] if optimizer_accepted else 1.0
        speedup_large = large_timing["speedup"] if optimizer_accepted else 1.0
        timing_note = "optimized" if optimizer_accepted else "unchanged SQL"

        record = {
            "id": q_id,
            "category": category,
            "question": question,
            "original_sql": sql,
            "candidate_sql": cand_sql,
            "optimized_sql": opt["optimized_sql"] if optimizer_accepted else sql,
            "optimizer_accepted": optimizer_accepted,
            "report_certified": report_certified,
            "reason": opt["reason"],
            "timing_note": timing_note,
            "llm_calls": opt["llm_calls"],
            "optimizer_ms": opt["latency_ms"],
            "small_db": {
                "before_ms": small_timing["before_ms"],
                "after_ms": small_timing["after_ms"] if optimizer_accepted else small_timing["before_ms"],
                "speedup": speedup_small,
                "results_equal": small_eq,
                "plan_improved": plan_improved_small,
                "raw_orig_ms": small_timing["raw_orig_ms"],
                "raw_opt_ms": small_timing["raw_opt_ms"],
                "status_orig": small_timing["status_orig"],
                "status_opt": small_timing["status_opt"],
                "plan_before": plan_before_small,
                "plan_after": plan_after_small,
            },
            "large_db": {
                "before_ms": large_timing["before_ms"],
                "after_ms": large_timing["after_ms"] if optimizer_accepted else large_timing["before_ms"],
                "speedup": speedup_large,
                "results_equal": large_eq,
                "plan_improved": plan_improved_large,
                "raw_orig_ms": large_timing["raw_orig_ms"],
                "raw_opt_ms": large_timing["raw_opt_ms"],
                "status_orig": large_timing["status_orig"],
                "status_opt": large_timing["status_opt"],
                "plan_before": plan_before_large,
                "plan_after": plan_after_large,
            },
        }
        records.append(record)

        tag = "ACCEPTED" if optimizer_accepted else "KEPT"
        cert_tag = "CERTIFIED" if report_certified else ("FAILED_SCALE" if optimizer_accepted else "N/A")
        print(f"[{n}/{len(cases)}] {q_id} ({category}): {tag} | Dual-Cert: {cert_tag}")

    # Summary metrics calculation
    queries_considered = len(records)
    triggers_fired = sum(1 for r in records if "Plan already reasonable" not in r["reason"])
    rewrites_proposed = sum(1 for r in records if r["candidate_sql"] is not None)
    optimizer_accepted_count = sum(1 for r in records if r["optimizer_accepted"])
    report_certified_count = sum(1 for r in records if r["report_certified"])

    # Rejection breakdown
    rejections: dict[str, int] = {}
    for r in records:
        if not r["optimizer_accepted"]:
            cat = categorize_rejection(r["reason"])
            rejections[cat] = rejections.get(cat, 0) + 1

    # Aggregate performance metrics (ONLY over report_certified == True queries)
    certified_records = [r for r in records if r["report_certified"]]
    certified_speedups = [
        r["large_db"]["speedup"]
        for r in certified_records
        if r["large_db"]["speedup"] is not None
    ]
    median_speedup_large = round(statistics.median(certified_speedups), 2) if certified_speedups else None

    certified_before_large = [
        r["large_db"]["before_ms"]
        for r in certified_records
        if r["large_db"]["before_ms"] is not None
    ]
    median_ms_before_large = round(statistics.median(certified_before_large), 2) if certified_before_large else None

    certified_after_large = [
        r["large_db"]["after_ms"]
        for r in certified_records
        if r["large_db"]["after_ms"] is not None
    ]
    median_ms_after_large = round(statistics.median(certified_after_large), 2) if certified_after_large else None

    dual_db_equality_rate = (
        f"{report_certified_count}/{optimizer_accepted_count}"
        if optimizer_accepted_count > 0
        else "N/A"
    )
    plan_improved_large_count = sum(
        1 for r in records if r["optimizer_accepted"] and r["large_db"]["plan_improved"]
    )
    plan_improved_large_rate = (
        f"{plan_improved_large_count}/{optimizer_accepted_count}"
        if optimizer_accepted_count > 0
        else "N/A"
    )

    summary = {
        "suite_label": suite_label,
        "timing_protocol": f"{args.warmups} warm-up + {args.runs} runs, interleaved; timeout {args.timeout}s",
        "small_database": str(small_db),
        "large_database": str(large_db),
        "queries_considered": queries_considered,
        "triggers_fired": triggers_fired,
        "rewrites_proposed": rewrites_proposed,
        "optimizer_accepted": optimizer_accepted_count,
        "report_certified": report_certified_count,
        "dual_db_equality_rate": dual_db_equality_rate,
        "plan_improved_large_rate": plan_improved_large_rate,
        "median_speedup_large_certified": median_speedup_large,
        "median_ms_before_large_certified": median_ms_before_large,
        "median_ms_after_large_certified": median_ms_after_large,
        "rejection_breakdown": rejections,
        "llm_calls": sum(r["llm_calls"] for r in records),
    }

    # Save artifacts
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = args.out / f"{artifact_prefix}_{stamp}"

    json_path = base.with_suffix(".json")
    json_path.write_text(
        json.dumps({"summary": summary, "queries": records}, indent=2), encoding="utf-8"
    )

    # Generate Markdown report
    summary_table = "\n".join(
        [
            f"| Metric | Value |",
            f"|---|---|",
            f"| Queries Considered | {queries_considered} |",
            f"| Triggers Fired | {triggers_fired} |",
            f"| Rewrites Proposed | {rewrites_proposed} |",
            f"| Optimizer Accepted | {optimizer_accepted_count} |",
            f"| Report Certified (Dual-DB Validated) | {report_certified_count} |",
            f"| Dual-DB Equality Rate | {dual_db_equality_rate} |",
            f"| Large DB Plan Improvement Rate | {plan_improved_large_rate} |",
            f"| Large DB Median Speedup (Certified) | {median_speedup_large}x |" if median_speedup_large else "| Large DB Median Speedup (Certified) | N/A |",
            f"| Large DB Median ms Before (Certified) | {median_ms_before_large} ms |" if median_ms_before_large else "| Large DB Median ms Before (Certified) | N/A |",
            f"| Large DB Median ms After (Certified) | {median_ms_after_large} ms |" if median_ms_after_large else "| Large DB Median ms After (Certified) | N/A |",
        ]
    )

    rejection_table = "\n".join(
        [f"| Rejection Category | Count |", f"|---|---|"]
        + [f"| {k} | {v} |" for k, v in sorted(rejections.items())]
    )

    query_rows = []
    for r in records:
        s_b = f"{r['small_db']['before_ms']:.2f}" if r['small_db']['before_ms'] is not None else "timeout"
        s_a = f"{r['small_db']['after_ms']:.2f}" if r['small_db']['after_ms'] is not None else "timeout"
        l_b = f"{r['large_db']['before_ms']:.2f}" if r['large_db']['before_ms'] is not None else "timeout"
        l_a = f"{r['large_db']['after_ms']:.2f}" if r['large_db']['after_ms'] is not None else "timeout"
        l_sp = f"{r['large_db']['speedup']:.2f}x" if r['large_db']['speedup'] is not None else "N/A"
        cert = "PASS" if r['report_certified'] else ("FAIL" if r['optimizer_accepted'] else "KEPT")
        query_rows.append(
            f"| {r['id']} | {r['category']} | {'ACCEPTED' if r['optimizer_accepted'] else 'KEPT'} | {cert} | "
            f"{s_b} -> {s_a} | {l_b} -> {l_a} | {l_sp} |"
        )

    queries_table = "\n".join(
        [
            f"| ID | Category | Optimizer | Dual-Cert | Small DB Before->After (ms) | Large DB Before->After (ms) | Large DB Speedup |",
            f"|---|---|---|---|---|---|---|",
        ]
        + query_rows
    )

    md_content = (
        f"# Optimizer Benchmark Report (Dual-Database Scale Evaluation)\n\n"
        f"**Suite:** {summary['suite_label']}\n\n"
        f"**Protocol:** {summary['timing_protocol']}\n\n"
        f"- **Small DB:** `{small_db}`\n"
        f"- **Large DB:** `{large_db}`\n\n"
        f"## Summary Metrics\n\n"
        f"{summary_table}\n\n"
        f"## Rejection Breakdown\n\n"
        f"{rejection_table}\n\n"
        f"## Query Results\n\n"
        f"{queries_table}\n"
    )

    md_path = base.with_suffix(".md")
    md_path.write_text(md_content, encoding="utf-8")

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nArtifacts persisted:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    return 0


# --- Legacy Spider Benchmark flow ---


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
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for t in tables:
                for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
                    conn.execute(f'CREATE INDEX IF NOT EXISTS "bx_{t}_{fk[3]}" ON "{t}"("{fk[3]}")')
                    made += 1
            conn.commit()
    return copy, made


def time_query(sql: str, db: Path) -> tuple[float | None, list, list]:
    """Legacy helper: median ms over WARMUPS+RUNS runs, plus rows and columns."""
    try:
        times = []
        for i in range(DEFAULT_WARMUPS + DEFAULT_RUNS):
            start = perf_counter()
            rows, cols = run_limited(sql, db, DEFAULT_TIMEOUT_S)
            if i >= DEFAULT_WARMUPS:
                times.append((perf_counter() - start) * 1000)
        return statistics.median(times), rows, cols
    except Exception:
        return None, [], []


def run_spider_benchmark(args: argparse.Namespace) -> int:
    """Run legacy optimizer benchmark on Spider dev gold SQL."""
    load_dotenv(ROOT / ".env")
    queries = pick_queries(args.spider, args.dbs, args.limit)
    rows_out, index_counts = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        copies = {}
        for q in queries:
            if q["db_id"] not in copies:
                copies[q["db_id"]], index_counts[q["db_id"]] = prepare_copy(
                    args.spider, q["db_id"], Path(tmp), args.index_fks
                )
        schemas = {i: introspect_schema(p) for i, p in copies.items()}
        for n, q in enumerate(queries, 1):
            db, sql = copies[q["db_id"]], q["query"]
            opt = optimize_sql(sql, q["question"], schemas[q["db_id"]], db_path=db)
            row = {
                "db_id": q["db_id"],
                "question": q["question"],
                "original_sql": sql,
                "changed": opt["changed"],
                "reason": opt["reason"],
                "llm_calls": opt["llm_calls"],
                "optimizer_ms": opt["latency_ms"],
                "optimized_sql": opt["optimized_sql"],
            }
            if opt["changed"]:
                before_ms, r_a, c_a = time_query(sql, db)
                after_ms, r_b, c_b = time_query(opt["sql"], db)
                row.update(
                    before_ms=before_ms,
                    after_ms=after_ms,
                    plan_improved=plan_improved(opt["plan_before"], opt["plan_after"]),
                    equal=before_ms is not None
                    and after_ms is not None
                    and compare_results(
                        r_a, c_a, r_b, c_b, ordered=has_top_level_order_by(sql)
                    ),
                )
            rows_out.append(row)
            print(f"[{n}/{len(queries)}] {q['db_id']}: {'REWRITTEN' if row['changed'] else 'kept'}")

    rewritten = [r for r in rows_out if r["changed"]]
    timed = [r for r in rewritten if r["before_ms"] is not None and r["after_ms"] is not None]
    summary = {
        "label": "PRELIMINARY: optimizer-only, Spider dev gold SQL, small subset",
        "index_fks_on_copies": args.index_fks,
        "indexes_added": index_counts,
        "databases": sorted(index_counts),
        "queries_considered": len(rows_out),
        "queries_rewritten": len(rewritten),
        "equality_maintained": f"{sum(r['equal'] for r in rewritten)}/{len(rewritten)}",
        "plan_improved": f"{sum(r['plan_improved'] for r in rewritten)}/{len(rewritten)}",
        "median_ms_before_rewritten": median([r["before_ms"] for r in timed]),
        "median_ms_after_rewritten": median([r["after_ms"] for r in timed]),
        "llm_calls": sum(r["llm_calls"] for r in rows_out),
        "timing": f"{DEFAULT_WARMUPS} warm-up + {DEFAULT_RUNS} runs, median; time limit {DEFAULT_TIMEOUT_S}s",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "indexed" if args.index_fks else "asis"
    base = args.out / f"optimizer_benchmark_{tag}_{stamp}"
    base.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "queries": rows_out}, indent=2), encoding="utf-8"
    )
    table = "\n".join(
        f"| {k} | {v} |"
        for k, v in summary.items()
        if k
        in (
            "queries_considered",
            "queries_rewritten",
            "equality_maintained",
            "plan_improved",
            "median_ms_before_rewritten",
            "median_ms_after_rewritten",
            "llm_calls",
        )
    )
    base.with_suffix(".md").write_text(
        f"# Optimizer benchmark ({summary['label']})\n\n"
        f"Databases: {', '.join(summary['databases'])}. FK indexes added to copies: "
        f"{args.index_fks}. {summary['timing']}.\n\n| Metric | Value |\n| --- | --- |\n{table}\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print("saved:", base.with_suffix(".json"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["dual", "spider"],
        default="dual",
        help="Benchmark mode: 'dual' (small + large synthetic DB) or 'spider' (Spider dev subset)",
    )
    parser.add_argument(
        "--small-db",
        type=Path,
        default=ROOT / "data" / "analytics.db",
        help="Path to small stakeholder SQLite database",
    )
    parser.add_argument(
        "--large-db",
        type=Path,
        default=ROOT / "data" / "large_analytics.db",
        help="Path to large synthetic SQLite database",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "eval" / "optimizer_cases.yaml",
        help="Path to YAML or JSON benchmark query file",
    )
    parser.add_argument(
        "--traces",
        type=Path,
        default=None,
        help="Path to QueryMind JSONL trace file to benchmark frozen system SQL",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
        help="Optional path to pre-generated candidates JSON file",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help="Number of measured timing runs (default 5)",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=DEFAULT_WARMUPS,
        help="Number of warmup runs (default 1)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="Execution timeout in seconds per query run (default 30.0)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "eval" / "results",
        help="Directory to save benchmark JSON and MD reports",
    )

    # Spider-specific arguments
    parser.add_argument(
        "--spider",
        type=Path,
        default=ROOT / "data" / "spider_data",
        help="Spider dataset directory",
    )
    parser.add_argument(
        "--dbs", type=int, default=3, help="How many largest dev DBs (spider mode)"
    )
    parser.add_argument(
        "--limit", type=int, default=30, help="Total queries (spider mode)"
    )
    parser.add_argument(
        "--index-fks",
        action="store_true",
        help="Index FK columns on copies (spider mode)",
    )

    args = parser.parse_args(argv)

    if args.mode == "spider":
        return run_spider_benchmark(args)
    return run_dual_benchmark(args)


if __name__ == "__main__":
    raise SystemExit(main())
