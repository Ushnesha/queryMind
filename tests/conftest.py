"""Offline isolation and disposable database fixtures shared across branches."""

from pathlib import Path
import socket

import pytest

from scripts.seed_db import seed_database


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make accidental external network use fail, even on credentialed machines."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    for name in ("OPENCODE_API_KEY", "OPENAI_API_KEY", "NEO4J_PASSWORD", "SQLITE_DB", "QUERYMIND_PROVIDER"):
        monkeypatch.delenv(name, raising=False)

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Unit tests must run without network access")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a deterministic SQLite fixture outside the checked-in data tree."""
    return seed_database(tmp_path / "analytics.db")
