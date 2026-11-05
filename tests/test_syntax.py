"""SQLite preparation validates syntax and references without execution."""

from src.verifiers import check_syntax


def test_syntax_contract(db_path) -> None:
    assert check_syntax("SELECT * FROM customers", db_path=db_path) == {
        "ok": True,
        "error": None,
    }


def test_syntax_rejects_invalid_statement(db_path) -> None:
    result = check_syntax("SELECT FROM customers", db_path=db_path)
    assert result["ok"] is False
    assert result["error"]


def test_syntax_rejects_missing_column(db_path) -> None:
    result = check_syntax("SELECT nonexistent_column FROM customers", db_path=db_path)
    assert result["ok"] is False
    assert result["error"]
