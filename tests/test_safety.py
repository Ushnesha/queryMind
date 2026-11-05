"""Read-only policy contracts independent of any external services."""

import pytest

from src.db import execute_sql
from src.verifiers import check_safety


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "UPDATE customers SET name = 'changed'",
        "SELECT 1; DROP TABLE customers",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE ':memory:' AS other",
    ],
)
def test_safety_rejects_mutation(sql: str) -> None:
    result = check_safety(sql)
    assert result["ok"] is False
    assert isinstance(result["error"], str)


def test_safety_accepts_read_query() -> None:
    assert check_safety("SELECT 1") == {"ok": True, "error": None}


def test_execution_enforces_safety_even_without_verifier(db_path) -> None:
    with pytest.raises(ValueError):
        execute_sql("DELETE FROM customers", db_path=db_path)
    assert execute_sql("SELECT COUNT(*) FROM customers", db_path=db_path)["rows"][0][0] > 0
