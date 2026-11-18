"""Tests for the large synthetic database generator (R5.1)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

from scripts.seed_db import seed_database
from scripts.seed_large_db import (
    GenerationSummary,
    main as seed_large_main,
    seed_large_database,
    validate_large_database,
)
from src.db import connect_readonly, execute_sql


def test_seed_large_database_small_scale(tmp_path: Path) -> None:
    """Fast check on small scale: creates valid schema and expected counts."""
    db_file = tmp_path / "small_test.db"
    summary = seed_large_database(db_file, customers=100, orders=500, seed=42)

    assert isinstance(summary, GenerationSummary)
    assert summary.customers == 100
    assert summary.orders == 500
    assert summary.inactive_customers > 0
    assert summary.active_customers + summary.inactive_customers == 100
    assert summary.total_spending > 0.0
    assert summary.min_order_amount >= 5.0
    assert summary.max_order_amount <= 3500.0
    assert db_file.is_file()
    assert summary.file_size_bytes > 0
    assert summary.generation_time_s >= 0.0

    # Validation helper should pass without errors
    validate_large_database(db_file, 100, 500, summary.synthetic_join_dates)


def test_schema_equivalence_with_demo_db(tmp_path: Path) -> None:
    """The large database schema and indexes must match the demo database exactly."""
    demo_db = tmp_path / "demo.db"
    large_db = tmp_path / "large.db"

    seed_database(demo_db)
    seed_large_database(large_db, customers=50, orders=100, seed=123)

    conn_demo = sqlite3.connect(demo_db)
    conn_large = sqlite3.connect(large_db)

    try:
        def get_schema(conn: sqlite3.Connection) -> dict[str, Any]:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()]
            info: dict[str, Any] = {"tables": tables, "columns": {}, "fks": {}, "indexes": {}}
            for t in tables:
                info["columns"][t] = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
                info["fks"][t] = conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()
                info["indexes"][t] = conn.execute(f'PRAGMA index_list("{t}")').fetchall()
            return info

        schema_demo = get_schema(conn_demo)
        schema_large = get_schema(conn_large)

        assert schema_demo["tables"] == schema_large["tables"] == ["customers", "orders"]
        assert schema_demo["columns"] == schema_large["columns"]
        assert schema_demo["fks"] == schema_large["fks"]
        assert schema_demo["indexes"] == schema_large["indexes"] == {"customers": [], "orders": []}
    finally:
        conn_demo.close()
        conn_large.close()


def test_deterministic_generation(tmp_path: Path) -> None:
    """Same parameters and seed must produce identical rows in identical order."""
    db1 = tmp_path / "run1.db"
    db2 = tmp_path / "run2.db"

    seed_large_database(db1, customers=80, orders=300, seed=99)
    seed_large_database(db2, customers=80, orders=300, seed=99)

    conn1 = sqlite3.connect(db1)
    conn2 = sqlite3.connect(db2)
    try:
        customers1 = conn1.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
        customers2 = conn2.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
        assert customers1 == customers2

        orders1 = conn1.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
        orders2 = conn2.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
        assert orders1 == orders2
    finally:
        conn1.close()
        conn2.close()


def test_different_seeds_produce_different_data(tmp_path: Path) -> None:
    """Different seeds should generate different customer order assignments and amounts."""
    db1 = tmp_path / "seed1.db"
    db2 = tmp_path / "seed2.db"

    seed_large_database(db1, customers=50, orders=200, seed=42)
    seed_large_database(db2, customers=50, orders=200, seed=43)

    conn1 = sqlite3.connect(db1)
    conn2 = sqlite3.connect(db2)
    try:
        orders1 = conn1.execute("SELECT customer_id, amount, order_date FROM orders ORDER BY order_id").fetchall()
        orders2 = conn2.execute("SELECT customer_id, amount, order_date FROM orders ORDER BY order_id").fetchall()
        assert orders1 != orders2
    finally:
        conn1.close()
        conn2.close()


def test_temporal_causality_and_date_bounds(tmp_path: Path) -> None:
    """All orders must satisfy order_date >= synthetic_join_date and fall within 2023-2025."""
    db_file = tmp_path / "temporal.db"
    summary = seed_large_database(db_file, customers=100, orders=400, seed=77)

    conn = sqlite3.connect(db_file)
    try:
        min_date, max_date = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
        assert min_date >= "2023-01-01"
        assert max_date <= "2025-12-31"

        # Explicit check against the internal metadata
        for cid, o_date_str in conn.execute("SELECT customer_id, order_date FROM orders"):
            join_date = summary.synthetic_join_dates[cid]
            order_date = date.fromisoformat(o_date_str)
            assert order_date >= join_date
    finally:
        conn.close()


def test_inactive_customers_and_skewed_activity(tmp_path: Path) -> None:
    """Verify that ~15% inactive customers exist and customer order counts are skewed."""
    db_file = tmp_path / "skew.db"
    summary = seed_large_database(db_file, customers=200, orders=1000, seed=42)

    conn = sqlite3.connect(db_file)
    try:
        # Check inactive customers
        (inactive,) = conn.execute(
            "SELECT COUNT(*) FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id "
            "WHERE o.order_id IS NULL"
        ).fetchone()
        assert inactive > 0
        # Inactive percentage should be close to 15% (e.g. between 8% and 25% with random roll)
        inactive_pct = inactive / 200
        assert 0.08 <= inactive_pct <= 0.30

        # Check activity skew: power customers exist with significantly more orders than average
        counts = [
            r[0]
            for r in conn.execute(
                "SELECT COUNT(order_id) FROM orders GROUP BY customer_id ORDER BY COUNT(order_id) DESC"
            ).fetchall()
        ]
        top_order_count = counts[0]
        median_order_count = counts[len(counts) // 2]
        assert top_order_count > median_order_count * 2
    finally:
        conn.close()


def test_overwrite_behavior(tmp_path: Path) -> None:
    """Re-seeding without overwrite must raise FileExistsError; with overwrite must succeed."""
    db_file = tmp_path / "overwrite_test.db"

    seed_large_database(db_file, customers=20, orders=50, seed=1)
    assert db_file.exists()

    with pytest.raises(FileExistsError):
        seed_large_database(db_file, customers=20, orders=50, seed=2, overwrite=False)

    # With overwrite=True, succeeds
    summary = seed_large_database(db_file, customers=30, orders=60, seed=3, overwrite=True)
    assert summary.customers == 30
    assert summary.orders == 60


def test_readonly_executor_compatibility(tmp_path: Path) -> None:
    """The generated database must work with QueryMind's existing read-only executor."""
    db_file = tmp_path / "readonly_test.db"
    seed_large_database(db_file, customers=50, orders=100, seed=42)

    res = execute_sql("SELECT COUNT(*) AS total_customers FROM customers", db_path=db_file)
    assert res["columns"] == ["total_customers"]
    assert res["rows"] == [[50]]

    top = execute_sql(
        "SELECT c.name, SUM(o.amount) AS spending "
        "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
        "GROUP BY c.customer_id, c.name ORDER BY spending DESC LIMIT 3",
        db_path=db_file,
    )
    assert len(top["rows"]) == 3
    assert top["columns"] == ["name", "spending"]


def test_cli_execution(tmp_path: Path) -> None:
    """CLI invocation with custom arguments should succeed."""
    target_db = tmp_path / "cli_test.db"
    exit_code = seed_large_main([
        "--db", str(target_db),
        "--customers", "30",
        "--orders", "75",
        "--seed", "101",
        "--quiet",
    ])
    assert exit_code == 0
    assert target_db.exists()

    # Re-running without overwrite returns code 1
    exit_code_conflict = seed_large_main([
        "--db", str(target_db),
        "--customers", "30",
        "--orders", "75",
        "--seed", "101",
        "--quiet",
    ])
    assert exit_code_conflict == 1

    # Re-running with --overwrite returns code 0
    exit_code_overwrite = seed_large_main([
        "--db", str(target_db),
        "--customers", "40",
        "--orders", "80",
        "--seed", "101",
        "--overwrite",
        "--quiet",
    ])
    assert exit_code_overwrite == 0
