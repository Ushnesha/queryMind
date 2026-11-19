"""Fast, offline unit tests for R5.4 poster artifacts, trace ingestion, and questions."""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.benchmark_optimizer import load_trace_cases
from scripts.plot_optimizer_poster import (
    plot_optimizer_plan_example,
    plot_optimizer_timing,
)


@pytest.fixture
def sample_trace_file(tmp_path):
    """Create a temporary JSONL trace file containing stakeholder and agent-state records."""
    trace_path = tmp_path / "test_trace.jsonl"
    records = [
        # 1. Answerable query, optimization applied
        {
            "question_id": "H1",
            "question": "Show sales trends over time",
            "refused": False,
            "exec_ok": True,
            "qm_original_sql": "SELECT order_date, COUNT(DISTINCT order_id) FROM orders GROUP BY order_date",
            "sql": "SELECT order_date, COUNT(order_id) FROM orders GROUP BY order_date",
            "qm_optimization_applied": True,
            "qm_optimizer_rounds": 1,
            "category": "hard",
        },
        # 2. Answerable query, unoptimized (kept)
        {
            "question_id": "E1",
            "question": "How many customers are there?",
            "refused": False,
            "exec_ok": True,
            "qm_original_sql": "SELECT COUNT(*) FROM customers",
            "sql": "SELECT COUNT(*) FROM customers",
            "qm_optimization_applied": False,
            "qm_optimizer_rounds": 1,
            "category": "easy",
        },
        # 3. Refused query (should be skipped)
        {
            "question_id": "U1",
            "question": "What is the profit margin per product category?",
            "refused": True,
            "exec_ok": False,
            "sql": "NOT_ANSWERABLE:product cost",
            "qm_original_sql": "",
            "qm_optimization_applied": False,
            "category": "unanswerable",
        },
        # 4. Nested AgentState format
        {
            "question_id": "A1",
            "state": {
                "question": "Who are our best customers?",
                "status": "success",
                "original_sql": "SELECT name, SUM(amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id",
                "optimized_sql": "SELECT name, SUM(amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id",
                "optimization_applied": False,
            },
            "category": "ambiguous",
        },
    ]
    with trace_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return trace_path


@pytest.fixture
def sample_benchmark_json():
    """Create a minimal mock benchmark JSON payload for figure testing."""
    return {
        "summary": {
            "suite_label": "CONTROLLED_DEVELOPMENT_SUITE: R5.3 scenario validation suite",
            "queries_considered": 3,
            "triggers_fired": 2,
            "rewrites_proposed": 2,
            "optimizer_accepted": 1,
            "report_certified": 1,
            "dual_db_equality_rate": "1/1",
            "plan_improved_large_rate": "1/1",
            "median_speedup_large_certified": 4.5,
            "median_ms_before_large_certified": 90.0,
            "median_ms_after_large_certified": 20.0,
            "rejection_breakdown": {"already_optimal_skipped": 1, "distinct_guard_rejected": 1},
        },
        "queries": [
            {
                "id": "OPT01",
                "category": "correlated_subquery",
                "question": "Customers with orders",
                "original_sql": "SELECT c.customer_id FROM customers c WHERE (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id) > 0",
                "optimized_sql": "SELECT c.customer_id FROM customers c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)",
                "optimizer_accepted": True,
                "report_certified": True,
                "large_db": {
                    "before_ms": 90.0,
                    "after_ms": 20.0,
                    "speedup": 4.5,
                    "plan_before": [[1, 0, 0, "SCAN customers"], [2, 1, 0, "CORRELATED SUBQUERY"]],
                    "plan_after": [[1, 0, 0, "SCAN orders"], [2, 0, 0, "SEARCH customers USING INTEGER PRIMARY KEY"]],
                },
            },
            {
                "id": "OPT02",
                "category": "already_optimal",
                "question": "Customer by ID",
                "original_sql": "SELECT name FROM customers WHERE customer_id = 1",
                "optimized_sql": "SELECT name FROM customers WHERE customer_id = 1",
                "optimizer_accepted": False,
                "report_certified": False,
                "large_db": {
                    "before_ms": 0.1,
                    "after_ms": 0.1,
                    "speedup": 1.0,
                    "plan_before": [],
                    "plan_after": [],
                },
            },
        ],
    }


def test_load_trace_cases(sample_trace_file):
    """Test that trace ingestion extracts executable queries and handles rewrites properly."""
    cases = load_trace_cases(sample_trace_file)

    # Out of 4 records, 3 are answerable/executable, 1 was refused and filtered out
    assert len(cases) == 3

    # H1 had optimization applied
    h1 = next(c for c in cases if c["id"] == "H1")
    assert h1["candidate_rewrite"] is not None
    assert "COUNT(order_id)" in h1["candidate_rewrite"]
    assert "COUNT(DISTINCT" in h1["query"]

    # E1 was unoptimized
    e1 = next(c for c in cases if c["id"] == "E1")
    assert e1["candidate_rewrite"] is None
    assert "SELECT COUNT(*)" in e1["query"]

    # A1 was extracted from nested state
    a1 = next(c for c in cases if c["id"] == "A1")
    assert a1["candidate_rewrite"] is None
    assert "JOIN orders" in a1["query"]


def test_member5_questions_structure():
    """Verify that eval/new_questions/member5.yaml matches the exact team allocation."""
    q_path = Path("eval/new_questions/member5.yaml")
    assert q_path.exists(), "eval/new_questions/member5.yaml must exist"

    data = yaml.safe_load(q_path.read_text(encoding="utf-8"))
    assert "questions" in data
    questions = data["questions"]

    # Must have exactly 7 questions as allocated: 2 Easy, 3 Hard, 1 Unanswerable, 1 Ambiguous
    assert len(questions) == 7

    easy = [q for q in questions if q.get("difficulty") == "easy" and q.get("answerable") is True and not q.get("ambiguous")]
    hard = [q for q in questions if q.get("difficulty") == "hard" and q.get("answerable") is True and not q.get("ambiguous")]
    unanswerable = [q for q in questions if q.get("answerable") is False]
    ambiguous = [q for q in questions if q.get("ambiguous") is True]

    assert len(easy) == 2
    assert len(hard) == 3
    assert len(unanswerable) == 1
    assert len(ambiguous) == 1

    # Unanswerable has missing fields
    assert "missing_fields" in unanswerable[0]
    assert len(unanswerable[0]["missing_fields"]) > 0

    # Ambiguous has reference assumption
    assert "reference_assumption" in ambiguous[0]


def test_member5_questions_execute_sqlite():
    """Verify that every answerable question in member5.yaml executes without errors."""
    q_path = Path("eval/new_questions/member5.yaml")
    data = yaml.safe_load(q_path.read_text(encoding="utf-8"))

    with sqlite3.connect("data/analytics.db") as conn:
        for q in data["questions"]:
            if q.get("answerable"):
                sql = q["sql"]
                cursor = conn.execute(sql)
                # Ensure execution succeeds and returns results
                cursor.fetchall()


def test_plot_optimizer_timing_creates_pdf(tmp_path, sample_benchmark_json):
    """Verify that plot_optimizer_timing generates a valid vector PDF file."""
    out_pdf = tmp_path / "timing.pdf"
    plot_optimizer_timing(sample_benchmark_json, out_pdf, is_preview=True)

    assert out_pdf.exists()
    content = out_pdf.read_bytes()
    assert content.startswith(b"%PDF-1.4")
    assert b"QueryMind Optimizer: Execution Time at Scale" in content
    assert b"DEVELOPMENT PREVIEW" in content


def test_plot_optimizer_plan_creates_pdf(tmp_path, sample_benchmark_json):
    """Verify that plot_optimizer_plan_example generates a valid vector PDF file."""
    out_pdf = tmp_path / "plan.pdf"
    plot_optimizer_plan_example(sample_benchmark_json, out_pdf, is_preview=True)

    assert out_pdf.exists()
    content = out_pdf.read_bytes()
    assert content.startswith(b"%PDF-1.4")
    assert b"QueryMind Plan Transformation" in content
    assert b"DEVELOPMENT PREVIEW" in content


def test_plot_figures_zero_certified_graceful(tmp_path):
    """Verify graceful handling when 0 rewrites are certified (no ZeroDivisionError)."""
    empty_benchmark = {
        "summary": {
            "suite_label": "FROZEN_SYSTEM_TRACES: live_run.jsonl",
            "queries_considered": 2,
            "triggers_fired": 0,
            "rewrites_proposed": 0,
            "optimizer_accepted": 0,
            "report_certified": 0,
            "rejection_breakdown": {"already_optimal_skipped": 2},
        },
        "queries": [
            {
                "id": "Q1",
                "optimizer_accepted": False,
                "report_certified": False,
                "large_db": {"before_ms": 1.0, "after_ms": 1.0, "speedup": 1.0},
            }
        ],
    }
    t_pdf = tmp_path / "timing_empty.pdf"
    p_pdf = tmp_path / "plan_empty.pdf"

    plot_optimizer_timing(empty_benchmark, t_pdf, is_preview=False)
    plot_optimizer_plan_example(empty_benchmark, p_pdf, is_preview=False)

    assert t_pdf.exists() and t_pdf.read_bytes().startswith(b"%PDF-1.4")
    assert p_pdf.exists() and p_pdf.read_bytes().startswith(b"%PDF-1.4")
