"""Optimizer contract and shared equality semantics."""

import json
import sqlite3

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


# ---- equality gate ----
import pytest

from src.optimizer.equality import has_top_level_order_by, results_equal, run_limited


def test_compare_results_order_floats_and_nulls() -> None:
    from src.optimizer.equality import compare_results as cmp

    assert cmp([[1], [2]], ["a"], [[2], [1]], ["a"])
    assert not cmp([[1], [2]], ["a"], [[2], [1]], ["a"], ordered=True)
    assert cmp([[0.1 + 0.2]], ["a"], [[0.3]], ["a"])
    assert cmp([[None], [1]], ["a"], [[1], [None]], ["a"])
    assert not cmp([[None]], ["a"], [[0]], ["a"])


def test_top_level_order_by_detection() -> None:
    assert has_top_level_order_by("SELECT a FROM t ORDER BY a")
    assert not has_top_level_order_by("SELECT a FROM (SELECT a FROM t ORDER BY a)")
    assert not has_top_level_order_by("SELECT 'order by' FROM t")


def test_results_equal_same_and_different(db_path) -> None:
    a = "SELECT name FROM customers WHERE customer_id IN (SELECT customer_id FROM orders)"
    b = "SELECT DISTINCT c.name FROM customers c JOIN orders o ON c.customer_id = o.customer_id"
    assert results_equal(a, b, db_path)
    assert not results_equal(a, "SELECT name FROM customers", db_path)


def test_results_equal_respects_order_by(db_path) -> None:
    asc = "SELECT name FROM customers ORDER BY name"
    desc = "SELECT name FROM customers ORDER BY name DESC"
    assert not results_equal(asc, desc, db_path)
    assert results_equal("SELECT name FROM customers", desc, db_path)  # no ORDER BY: unordered


def test_results_equal_false_on_unsafe_or_bad_sql(db_path) -> None:
    ok = "SELECT 1"
    assert not results_equal(ok, "DROP TABLE customers", db_path)
    assert not results_equal(ok, "SELECT 1; SELECT 2", db_path)
    assert not results_equal(ok, "SELECT nope FROM nowhere", db_path)


SLOW = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100000000) "
    "SELECT COUNT(*) FROM c"
)


def test_timeout_is_enforced(db_path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        run_limited(SLOW, db_path, timeout_s=0.2)
    assert not results_equal("SELECT 1", SLOW, db_path, timeout_s=0.2)


# ---- optimize_sql end to end with a mocked LLM ----
import json as _json
from src.optimizer import optimize_sql as _opt

IN_SQL = "SELECT name FROM customers WHERE customer_id IN (SELECT customer_id FROM orders)"
GOOD = "SELECT DISTINCT c.name FROM customers c JOIN orders o ON c.customer_id = o.customer_id"


class FakeLLM:
    def __init__(self, reply="", error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def __call__(self, prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


def reply(sql):
    return _json.dumps({"sql": sql, "reason": "join instead of subquery"})


def run(db_path, llm, sql=IN_SQL, **kw):
    return _opt(sql, "Which customers ordered?", "schema", db_path=db_path, llm=llm, **kw)


def test_good_plan_no_llm_call(db_path) -> None:
    llm = FakeLLM(reply(GOOD))
    out = run(db_path, llm, sql="SELECT name FROM customers WHERE customer_id = 1")
    assert llm.calls == 0 and out["changed"] is False and out["llm_calls"] == 0
    assert out["equality_ok"] is None


CORR_SQL = (
    "SELECT name FROM customers c WHERE "
    "(SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id) > 1"
)
CORR_GOOD = (
    "SELECT c.name FROM customers c JOIN "
    "(SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) > 1) o "
    "ON c.customer_id = o.customer_id"
)


def test_equal_rewrite_with_better_plan_accepted(db_path) -> None:
    out = run(db_path, FakeLLM(reply(CORR_GOOD)), sql=CORR_SQL)
    assert out["changed"] and out["sql"] == out["optimized_sql"] == CORR_GOOD
    assert out["original_sql"] == CORR_SQL and out["equality_ok"] is True and out["llm_calls"] == 1
    assert out["plan_after"] != out["plan_before"]


def test_equal_rewrite_same_plan_quality_rejected(db_path) -> None:
    out = run(db_path, FakeLLM(reply(GOOD)))  # equal rows, but the plan is not better
    assert not out["changed"] and out["equality_ok"] is True


def test_different_rewrite_rejected(db_path) -> None:
    out = run(db_path, FakeLLM(reply("SELECT name FROM customers")))
    assert not out["changed"] and out["sql"] == IN_SQL and out["equality_ok"] is False
    assert out["optimized_sql"] == IN_SQL


@pytest.mark.parametrize(
    "bad", ["DELETE FROM orders", "SELECT 1; DROP TABLE orders", "SELECT x FROM nowhere"]
)
def test_unsafe_or_invalid_rewrite_rejected(db_path, bad) -> None:
    out = run(db_path, FakeLLM(reply(bad)))
    assert not out["changed"] and out["sql"] == IN_SQL and out["equality_ok"] is None


@pytest.mark.parametrize(
    "llm", [FakeLLM("garbage"), FakeLLM("{}"), FakeLLM(error=RuntimeError("down"))]
)
def test_llm_failure_returns_original(db_path, llm) -> None:
    out = run(db_path, llm)
    assert not out["changed"] and out["sql"] == IN_SQL


def test_slow_rewrite_hits_time_limit(db_path) -> None:
    out = run(db_path, FakeLLM(reply(SLOW)), timeout_s=0.2)
    assert not out["changed"] and out["sql"] == IN_SQL


def test_one_llm_attempt_per_call(db_path) -> None:
    llm = FakeLLM(reply("SELECT name FROM customers"))  # rejected, but no retry inside
    run(db_path, llm)
    assert llm.calls == 1


def test_optimize_never_raises_on_bad_input(db_path, tmp_path) -> None:
    assert not _opt("not sql", "q", "s", db_path=db_path)["changed"]
    assert not _opt(IN_SQL, "q", "s", db_path=tmp_path / "missing.db")["changed"]


def test_non_utf8_text_does_not_break_equality(tmp_path) -> None:
    path = tmp_path / "bad.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(a)")
    conn.execute("INSERT INTO t VALUES (CAST(x'ff41' AS TEXT))")
    conn.commit()
    conn.close()
    assert results_equal("SELECT a FROM t", "SELECT a FROM t ORDER BY a", path)


def test_equal_rewrite_without_plan_improvement_rejected(db_path) -> None:
    worse = IN_SQL + " ORDER BY customer_id"  # same rows, adds a sort, plan not better
    out = run(db_path, FakeLLM(reply(worse)))
    assert not out["changed"] and out["sql"] == IN_SQL
    assert out["equality_ok"] is True and "plan not improved" in out["reason"]
