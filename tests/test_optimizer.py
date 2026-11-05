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
