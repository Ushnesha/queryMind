"""Configuration paths and maximum budgets are part of the shared contract."""

from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, load_settings


def test_defaults_resolve_repository_paths() -> None:
    settings = load_settings()
    assert settings.database.path == PROJECT_ROOT / "data/analytics.db"
    assert settings.schema.default_mode == "neo4j" and settings.model.provider == "mock"


def test_sqlite_environment_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SQLITE_DB", str(tmp_path / "other.db"))
    assert load_settings().database.path == tmp_path / "other.db"


def test_provider_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("QUERYMIND_PROVIDER", "opencode")
    assert load_settings().model.provider == "opencode"
    monkeypatch.setenv("QUERYMIND_PROVIDER", "")
    assert load_settings().model.provider == "mock"


def test_invalid_budget_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("orchestrator:\n  max_repairs: 4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_repairs"):
        load_settings(path)
