"""Result verifier: deterministic sanity warnings and the optional LLM contradiction check."""

import json

import pytest

from src.verifiers import verify_result

SCHEMA = """TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT
)

TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  order_date TEXT NOT NULL
)"""

TOP3_SQL = "SELECT c.name, SUM(o.amount) AS total_spending FROM customers c JOIN orders o USING (customer_id) GROUP BY c.name ORDER BY total_spending DESC LIMIT 3"


class FakeJudge:
    def __init__(self, reply: object) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def generate(self, question: str, schema_context: str) -> str:
        self.calls.append((question, schema_context))
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply)


def run(question: str, sql: str, rows, columns, **kwargs):
    kwargs.setdefault("use_llm", False)
    return verify_result(question, sql, rows, columns, **kwargs)


def codes(result) -> set[str]:
    return {warning.split(":", 1)[0] for warning in result["warnings"]}


def test_clean_result_passes_with_statistics() -> None:
    rows = [["Alice Chen", 300.0], ["Bob Smith", 175.0], ["Carol Davis", 75.0]]
    result = run("Who are the top 3 customers by total spending?", TOP3_SQL, rows, ["name", "total_spending"], schema_context=SCHEMA)
    assert result["ok"] is True and result["warnings"] == []
    assert result["status"] == "deterministic"
    stats = result["statistics"]
    assert stats["row_count"] == 3 and stats["null_fraction"] == 0 and stats["duplicate_count"] == 0
    assert stats["numeric_columns"] == ["total_spending"]


def test_count_scalar_passes() -> None:
    result = run("How many customers are there?", "SELECT COUNT(*) AS customer_count FROM customers", [[4]], ["customer_count"])
    assert result["ok"] is True and result["warnings"] == []


def test_malformed_rows_fail() -> None:
    result = run("How many?", "SELECT 2", [[1, 2]], ["count"])
    assert result["ok"] is False and codes(result) == {"MALFORMED_ROWS"}


def test_empty_result_warns_without_failing() -> None:
    result = run("Which customers?", "SELECT * FROM customers", [], ["id"])
    assert result["ok"] is True and "EMPTY_RESULT" in codes(result)
    assert any("no rows" in warning for warning in result["warnings"])


def test_all_zero_result_warns() -> None:
    result = run("What is the total order amount per customer?", "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id",
                 [["a", 0], ["b", 0.0]], ["customer_id", "SUM(amount)"])
    assert "ALL_ZERO_RESULT" in codes(result)


def test_null_heavy_column_warns() -> None:
    rows = [["Alice", None], ["Bob", None], ["Carol", "c@x.com"]]
    result = run("List customer emails", "SELECT name, email FROM customers", rows, ["name", "email"])
    assert "NULL_HEAVY_COLUMN" in codes(result)
    assert result["statistics"]["column_null_fractions"]["email"] == pytest.approx(0.6667)


def test_null_scalar_aggregate_warns() -> None:
    result = run("What is the average order amount?", "SELECT AVG(amount) FROM orders", [[None]], ["AVG(amount)"])
    assert {"NULL_HEAVY_COLUMN", "NON_NUMERIC_AGGREGATE"} <= codes(result)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {"type": "nonfinite_float", "value": "-inf"}])
def test_non_finite_values_warn(value) -> None:
    result = run("What is the average ratio?", "SELECT AVG(x) AS ratio FROM t", [[value]], ["ratio"])
    assert "NON_FINITE_VALUE" in codes(result)


def test_top_n_row_limit_exceeded_warns() -> None:
    rows = [[f"c{i}", 10.0 - i] for i in range(5)]
    result = run("Who are the top 3 customers by total spending?", TOP3_SQL, rows, ["name", "total_spending"])
    assert "ROW_LIMIT_EXCEEDED" in codes(result)


def test_fewer_rows_than_requested_warns() -> None:
    result = run("Who are the top 3 customers by total spending?", TOP3_SQL, [["Alice", 300.0]], ["name", "total_spending"])
    assert "FEWER_ROWS_THAN_REQUESTED" in codes(result)


def test_how_many_expects_single_row() -> None:
    result = run("How many orders are there?", "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id",
                 [[1, 2], [2, 3]], ["customer_id", "COUNT(*)"])
    assert "EXPECTED_SINGLE_ROW" in codes(result)


def test_grouped_count_is_not_forced_to_one_row() -> None:
    result = run("How many orders per customer?", "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id",
                 [[1, 2], [2, 3]], ["customer_id", "COUNT(*)"])
    assert "EXPECTED_SINGLE_ROW" not in codes(result)


def test_non_numeric_aggregate_warns() -> None:
    result = run("What is the average order amount?", "SELECT name FROM customers", [["Alice"]], ["name"])
    assert "NON_NUMERIC_AGGREGATE" in codes(result)


def test_negative_count_warns() -> None:
    result = run("How many customers are there?", "SELECT -1 AS n", [[-1]], ["n"])
    assert "NEGATIVE_COUNT" in codes(result)


def test_duplicate_rows_warn() -> None:
    result = run("List customer names", "SELECT name FROM customers", [["Alice"], ["Alice"], ["Bob"]], ["name"])
    assert "DUPLICATE_ROWS" in codes(result) and result["statistics"]["duplicate_count"] == 1


def test_duplicate_columns_warn() -> None:
    result = run("List ids", "SELECT id, id FROM t", [[1, 1]], ["id", "id"])
    assert "DUPLICATE_COLUMNS" in codes(result)


def test_schema_consistency_accepts_columns_aliases_and_expressions() -> None:
    sql = "SELECT name, COUNT(*), SUM(amount) AS total FROM customers JOIN orders USING (customer_id) GROUP BY name"
    result = run("Orders per customer", sql, [["Alice", 2, 300.0]], ["name", "COUNT(*)", "total"], schema_context=SCHEMA)
    assert "UNKNOWN_RESULT_COLUMN" not in codes(result)


def test_schema_consistency_flags_unknown_column() -> None:
    result = run("List customers", "SELECT name, loyalty FROM customers", [["Alice", "gold"]], ["name", "loyalty"], schema_context=SCHEMA)
    assert "UNKNOWN_RESULT_COLUMN" in codes(result) and "loyalty" in result["warnings"][-1]


def test_schema_check_skipped_without_schema_context() -> None:
    result = run("List customers", "SELECT loyalty FROM customers", [["gold"]], ["loyalty"])
    assert "UNKNOWN_RESULT_COLUMN" not in codes(result)


def test_llm_contradiction_adds_warning_but_keeps_ok() -> None:
    judge = FakeJudge({"plausible": False, "reason": "Total spending cannot be an email address."})
    result = verify_result("Who are the top 3 customers by total spending?", TOP3_SQL,
                           [["Alice", "a@x.com"]], ["name", "email"], provider=judge)
    assert result["ok"] is True and result["status"] == "deterministic+llm"
    assert "SEMANTIC_CONTRADICTION" in codes(result)
    question, prompt = judge.calls[0]
    assert '"row_count": 1' in prompt and '"columns": ["name", "email"]' in prompt


def test_llm_plausible_adds_nothing() -> None:
    result = verify_result("How many customers are there?", "SELECT COUNT(*) FROM customers", [[4]], ["COUNT(*)"],
                           provider=FakeJudge({"plausible": True, "reason": "A count of 4 is plausible."}))
    assert result["warnings"] == [] and result["status"] == "deterministic+llm"


def test_llm_failure_is_recorded_not_raised() -> None:
    result = verify_result("How many customers are there?", "SELECT COUNT(*) FROM customers", [[4]], ["COUNT(*)"],
                           provider=FakeJudge(ValueError("timeout")))
    assert result["ok"] is True and result["status"] == "deterministic"
    assert "timeout" in result["statistics"]["llm_judge_error"]
