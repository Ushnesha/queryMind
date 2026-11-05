"""Contracts for shared read-only data access and mechanical scoring."""

from contextlib import closing
import json
import sqlite3

import pytest

from scripts.seed_db import seed_database
from src.db import connect_readonly, execute_sql, validate_readonly
from src.score import results_equal


@pytest.fixture
def database(tmp_path):
    return seed_database(tmp_path / "analytics.db")


def test_executor_result_contract(database):
    result = execute_sql("SELECT COUNT(*) AS customer_count FROM customers", db_path=database)
    assert result["rows"] == [[4]]
    assert result["columns"] == ["customer_count"]
    assert result["execution_time_ms"] >= 0


@pytest.mark.parametrize("sql", [
    "DELETE FROM customers", "SELECT 1; DROP TABLE customers", "PRAGMA query_only=OFF",
    "WITH x AS (SELECT 1) DELETE FROM customers", "SELECT load_extension('file')",
])
def test_guard_rejects_mutation(sql):
    with pytest.raises(ValueError):
        validate_readonly(sql)


def test_guard_understands_strings_and_comments(database):
    result = execute_sql("-- harmless\nSELECT 'delete; update' AS text;", db_path=database)
    assert result["rows"] == [["delete; update"]]


def test_connection_blocks_writes_even_without_guard(database):
    with closing(connect_readonly(database)) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("DELETE FROM customers")
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("PRAGMA query_only=OFF")


def test_missing_database_is_never_created(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        connect_readonly(missing)
    assert not missing.exists()


def test_seed_preserves_existing_file(database):
    original = database.read_bytes()
    with pytest.raises(FileExistsError):
        seed_database(database)
    assert database.read_bytes() == original


def test_result_equality_preserves_duplicate_counts():
    assert results_equal([[2], [1], [1]], ["n"], [[1], [2], [1]], ["n"])
    assert not results_equal([[1], [1]], ["n"], [[1]], ["n"])


def test_blob_cells_remain_distinct_from_text(database):
    blob = execute_sql("SELECT X'0061' AS value", db_path=database)
    text = execute_sql("SELECT '0061' AS value", db_path=database)
    assert blob["rows"] == [[{"type": "blob", "hex": "0061"}]]
    json.dumps(blob, allow_nan=False)
    assert not results_equal(blob["rows"], blob["columns"], text["rows"], text["columns"])


def test_nonfinite_float_cells_support_strict_json(database):
    result = execute_sql("SELECT 1e999 AS value", db_path=database)
    assert result["rows"] == [[{"type": "nonfinite_float", "value": "inf"}]]
    json.dumps(result, allow_nan=False)
