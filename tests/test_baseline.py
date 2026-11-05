"""New baseline's deterministic offline smoke checks."""

import pytest

from scripts.seed_db import seed_database
from src.baseline import run_baseline
from src.llm import MockProvider, get_provider


def test_baseline_demo_runs_without_credentials(tmp_path):
    database = seed_database(tmp_path / "analytics.db")
    result = run_baseline("Who are the top 3 customers by total spending?", db_path=database)
    assert result["rows"] == [["Alice Chen", 300.0], ["Bob Smith", 175.0], ["Carol Davis", 75.0]]
    assert result["columns"] == ["name", "total_spending"]


def test_mock_refuses_unsupported_questions():
    with pytest.raises(ValueError, match="offline mock"):
        MockProvider().generate("What is tomorrow's weather?", "")


def test_provider_does_not_silently_enable_network():
    with pytest.raises(ValueError, match="not implemented"):
        get_provider("remote")
