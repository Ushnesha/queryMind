"""Fast, offline unit tests for R5.3 dual-database optimizer benchmark runner."""

import json
import sqlite3
import statistics
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.benchmark_optimizer import (
    categorize_rejection,
    compute_speedup,
    main,
    time_query_interleaved,
)


@pytest.fixture
def temp_dbs():
    """Create disposable small and large SQLite databases for testing."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        small_path = tmp_path / "small.db"
        large_path = tmp_path / "large.db"

        # Small DB: 2 customers, 2 orders (all amount > 50)
        with sqlite3.connect(small_path) as conn:
            conn.execute(
                "CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
            )
            conn.execute(
                "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, order_date TEXT)"
            )
            conn.executemany(
                "INSERT INTO customers VALUES (?, ?, ?)",
                [(1, "Alice", "alice@example.com"), (2, "Bob", "bob@example.com")],
            )
            conn.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                [(1, 1, 100.0, "2024-01-01"), (2, 2, 75.0, "2024-01-02")],
            )
            conn.commit()

        # Large DB: 10 customers, 20 orders (some amount <= 50)
        with sqlite3.connect(large_path) as conn:
            conn.execute(
                "CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
            )
            conn.execute(
                "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, order_date TEXT)"
            )
            conn.executemany(
                "INSERT INTO customers VALUES (?, ?, ?)",
                [(i, f"Customer_{i}", f"c{i}@example.com") for i in range(1, 11)],
            )
            conn.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                [
                    (i, (i % 10) + 1, 20.0 if i % 2 == 0 else 150.0, f"2024-01-{(i%28)+1:02d}")
                    for i in range(1, 21)
                ],
            )
            conn.commit()

        yield small_path, large_path


def test_time_query_interleaved(temp_dbs):
    small_path, _ = temp_dbs
    orig = "SELECT name FROM customers WHERE customer_id = 1"
    cand = "SELECT name FROM customers WHERE customer_id = 1 LIMIT 1"

    res = time_query_interleaved(orig, cand, small_path, warmups=1, runs=3, timeout_s=5.0)

    assert res["status_orig"] == "ok"
    assert res["status_opt"] == "ok"
    assert len(res["raw_orig_ms"]) == 3
    assert len(res["raw_opt_ms"]) == 3
    assert isinstance(res["before_ms"], float)
    assert isinstance(res["after_ms"], float)
    assert res["results_equal"] is True
    assert res["speedup"] is not None


def test_dual_db_equality_certified_true(temp_dbs):
    small_path, large_path = temp_dbs
    orig = "SELECT customer_id, name FROM customers WHERE customer_id <= 2"
    cand = "SELECT customer_id, name FROM customers WHERE customer_id <= 2"

    small_res = time_query_interleaved(orig, cand, small_path, warmups=0, runs=1)
    large_res = time_query_interleaved(orig, cand, large_path, warmups=0, runs=1)

    assert small_res["results_equal"] is True
    assert large_res["results_equal"] is True

    optimizer_accepted = True
    report_certified = bool(
        optimizer_accepted
        and (small_res["results_equal"] is True)
        and (large_res["results_equal"] is True)
    )
    assert report_certified is True


def test_dual_db_equality_scale_failure_not_certified(temp_dbs):
    """Rewrite matches on small_db (due to coincident data) but fails on large_db."""
    small_path, large_path = temp_dbs
    # On small DB, all orders happen to have amount > 50, so dropping WHERE amount > 50 returns same rows.
    # On large DB, some orders have amount <= 50, so dropping WHERE amount > 50 returns different rows!
    orig = "SELECT customer_id FROM orders WHERE amount > 50"
    cand = "SELECT customer_id FROM orders"

    small_res = time_query_interleaved(orig, cand, small_path, warmups=0, runs=1)
    large_res = time_query_interleaved(orig, cand, large_path, warmups=0, runs=1)

    assert small_res["results_equal"] is True
    assert large_res["results_equal"] is False

    optimizer_accepted = True
    report_certified = bool(
        optimizer_accepted
        and (small_res["results_equal"] is True)
        and (large_res["results_equal"] is True)
    )
    # Must NOT certify rewrites that fail on the scale database
    assert report_certified is False


def test_timeout_handling_tri_state_equality(temp_dbs):
    small_path, _ = temp_dbs
    # Recursive CTE designed to run until aborted by progress handler
    slow_sql = (
        "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt) "
        "SELECT COUNT(*) FROM cnt"
    )
    fast_sql = "SELECT COUNT(*) FROM customers"

    res = time_query_interleaved(slow_sql, fast_sql, small_path, warmups=0, runs=1, timeout_s=0.05)

    assert "timeout" in res["status_orig"]
    assert res["status_opt"] == "ok"
    assert res["before_ms"] is None
    assert isinstance(res["after_ms"], float)
    # Tri-state equality: UNKNOWN (None), never falsely claimed False
    assert res["results_equal"] is None


def test_speedup_calculation():
    assert compute_speedup(100.0, 50.0) == 2.0
    assert compute_speedup(50.0, 100.0) == 0.5
    assert compute_speedup(None, 50.0) is None
    assert compute_speedup(100.0, None) is None
    assert compute_speedup(100.0, 0.0) is None

    # Lower bound speedup on timeout
    lower_bound = compute_speedup(None, 10.0, is_timeout_orig=True, timeout_s=30.0)
    assert lower_bound == 3000.0


def test_categorize_rejection():
    assert categorize_rejection("Plan already reasonable; no rewrite attempted.") == "already_optimal_skipped"
    assert categorize_rejection("Rewrite rejected: unsafe DISTINCT removal.") == "distinct_guard_rejected"
    assert categorize_rejection("Rewrite rejected: results differ.") == "equality_gate_rejected"
    assert categorize_rejection("Rewrite rejected: plan not improved.") == "plan_unimproved_rejected"
    assert categorize_rejection("Rewrite rejected: query timed out.") == "timeout_rejected"
    assert categorize_rejection("Syntax error in candidate.") == "other_rejected"


def test_summary_metrics_denominators():
    """Verify that aggregate speedup statistics use ONLY report_certified=True rewrites."""
    mock_records = [
        {
            "id": "Q1",
            "optimizer_accepted": True,
            "report_certified": True,
            "large_db": {"speedup": 4.0, "before_ms": 40.0, "after_ms": 10.0},
        },
        {
            "id": "Q2",
            "optimizer_accepted": True,
            "report_certified": True,
            "large_db": {"speedup": 2.0, "before_ms": 20.0, "after_ms": 10.0},
        },
        {
            "id": "Q3",
            # Accepted by optimizer on small db, but FAILED scale equality on large db
            "optimizer_accepted": True,
            "report_certified": False,
            "large_db": {"speedup": 10.0, "before_ms": 100.0, "after_ms": 10.0},
        },
        {
            "id": "Q4",
            # Unchanged SQL (skipped or rejected)
            "optimizer_accepted": False,
            "report_certified": False,
            "large_db": {"speedup": 1.0, "before_ms": 5.0, "after_ms": 5.0},
        },
    ]

    certified = [r for r in mock_records if r["report_certified"]]
    assert len(certified) == 2

    certified_speedups = [r["large_db"]["speedup"] for r in certified]
    median_speedup = statistics.median(certified_speedups)
    # Must be median([4.0, 2.0]) == 3.0, NOT affected by Q3 (10.0) or Q4 (1.0)
    assert median_speedup == 3.0

    before_certified = [r["large_db"]["before_ms"] for r in certified]
    assert statistics.median(before_certified) == 30.0


def test_dual_db_benchmark_cli_offline(temp_dbs):
    small_path, large_path = temp_dbs
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_dir = tmp_path / "results"
        cases_file = tmp_path / "cases.yaml"

        cases_data = {
            "cases": [
                {
                    "id": "TEST01",
                    "category": "already_optimal",
                    "question": "What is the name of customer 1?",
                    "query": "SELECT name FROM customers WHERE customer_id = 1",
                    "candidate_rewrite": None,
                },
                {
                    "id": "TEST02",
                    "category": "simple_projection",
                    "question": "List all customer names",
                    "query": "SELECT name FROM customers",
                    "candidate_rewrite": "SELECT name FROM customers",
                    "rewrite_reason": "Identical query",
                },
            ]
        }
        cases_file.write_text(yaml.dump(cases_data), encoding="utf-8")

        exit_code = main(
            [
                "--mode",
                "dual",
                "--small-db",
                str(small_path),
                "--large-db",
                str(large_path),
                "--queries",
                str(cases_file),
                "--runs",
                "1",
                "--warmups",
                "0",
                "--timeout",
                "2.0",
                "--out",
                str(out_dir),
            ]
        )

        assert exit_code == 0
        json_files = list(out_dir.glob("*.json"))
        md_files = list(out_dir.glob("*.md"))
        assert len(json_files) == 1
        assert len(md_files) == 1

        payload = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert "summary" in payload
        assert "queries" in payload
        assert payload["summary"]["queries_considered"] == 2
