"""Read-only policy contracts independent of any external services."""

import pytest

from src.db import execute_sql
from src.verifiers import check_safety


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO customers (name) VALUES ('x')",
        "DELETE FROM customers",
        "UPDATE customers SET name = 'changed'",
        "DROP TABLE customers",
        "ALTER TABLE customers ADD COLUMN age INTEGER",
        "CREATE TABLE copy AS SELECT * FROM customers",
        "REPLACE INTO customers (customer_id, name) VALUES (1, 'x')",
        "SELECT 1; DROP TABLE customers",
        "SELECT 1; SELECT 2",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE ':memory:' AS other",
        "WITH t AS (SELECT 1) DELETE FROM customers",
        "SELECT load_extension('evil')",
    ],
)
def test_safety_rejects_mutation(sql: str) -> None:
    result = check_safety(sql)
    assert result["ok"] is False
    assert isinstance(result["error"], str)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT 1;",
        "WITH totals AS (SELECT 1 AS n) SELECT n FROM totals",
        "SELECT 'DELETE FROM customers' AS harmless_text",
        "select name from customers -- drop table customers",
    ],
)
def test_safety_accepts_read_query(sql: str) -> None:
    assert check_safety(sql) == {"ok": True, "error": None}


def test_execution_enforces_safety_even_without_verifier(db_path) -> None:
    with pytest.raises(ValueError):
        execute_sql("DELETE FROM customers", db_path=db_path)
    assert execute_sql("SELECT COUNT(*) FROM customers", db_path=db_path)["rows"][0][0] > 0
