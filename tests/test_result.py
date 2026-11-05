"""Result contract checks table shape and reports limited coverage."""

from src.verifiers import verify_result


def test_result_contract() -> None:
    result = verify_result("How many?", "SELECT 2 AS count", [[2]], ["count"])
    assert result["ok"] is True
    assert isinstance(result["warnings"], list)
    assert result["statistics"] == {"row_count": 1, "column_count": 1}
    assert result["status"] == "placeholder"


def test_result_rejects_malformed_rows() -> None:
    result = verify_result("How many?", "SELECT 2", [[1, 2]], ["count"])
    assert result["ok"] is False


def test_result_empty_table_warns_without_fabricating_failure() -> None:
    result = verify_result("Which customers?", "SELECT * FROM customers", [], ["id"])
    assert result["ok"] is True
    assert any("no rows" in warning for warning in result["warnings"])
