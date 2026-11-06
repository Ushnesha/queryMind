"""Optimizer contract and shared equality semantics."""

import json

from src.optimizer import compare_results, explain_query_plan, optimize_sql


def test_optimizer_preserves_sql_and_returns_plan(db_path) -> None:
    sql = "SELECT COUNT(*) FROM customers"
    result = optimize_sql(sql, "How many customers?", "customers(id)", db_path=db_path)
    assert result["changed"] is False
    assert result["sql"] == sql
    assert result["plan_before"]
    assert result["plan_before"] == result["plan_after"]
    assert result["original_sql"] == result["optimized_sql"] == sql
    assert result["equality_ok"] is None
    assert result["llm_calls"] == 0
    assert isinstance(result["latency_ms"], int)
    json.dumps(result)


def test_explain_plan_is_json_serializable(db_path) -> None:
    plan = explain_query_plan("SELECT * FROM customers", db_path=db_path)
    assert isinstance(plan, list)
    assert plan
    json.dumps(plan)


def test_equality_preserves_duplicate_multiplicity() -> None:
    assert compare_results([[1], [2]], ["id"], [[2], [1]], ["id"])
    assert not compare_results([[1], [1]], ["id"], [[1]], ["id"])
    assert not compare_results([[1]], ["id"], [[1]], ["other_id"])


# ---- plan parser ----
from src.optimizer.explain import plan_improved, plan_signals


def _plan(*details: str) -> list[list]:
    return [[i, 0, 0, d] for i, d in enumerate(details)]


def test_plan_parser_handles_old_and_new_scan_format() -> None:
    new = plan_signals(_plan("SCAN orders"))
    old = plan_signals(_plan("SCAN TABLE orders"))
    assert new["scans"] == old["scans"] == 1
    assert new["scanned_tables"] == old["scanned_tables"] == ["orders"]
    assert plan_signals(_plan("SEARCH TABLE orders USING INDEX i (a=?)"))["searches"] == 1


def test_plan_signals_index_temp_btree_and_constant_row() -> None:
    s = plan_signals(_plan(
        "SEARCH c USING COVERING INDEX ix (a=?)", "USE TEMP B-TREE FOR ORDER BY", "SCAN CONSTANT ROW"
    ))
    assert (s["index_uses"], s["temp_btrees"], s["scans"]) == (1, 1, 0)


def test_plan_improved_rules() -> None:
    assert plan_improved(_plan("SCAN t"), _plan("SEARCH t USING INDEX i (a=?)"))
    assert plan_improved(_plan("SCAN t", "USE TEMP B-TREE FOR DISTINCT"), _plan("SCAN t"))
    assert not plan_improved(_plan("SCAN t"), _plan("SCAN t"))
    assert not plan_improved(_plan("SEARCH t USING INDEX i (a=?)"), _plan("SCAN t"))
