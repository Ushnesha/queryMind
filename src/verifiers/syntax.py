"""SQLite preparation checks that never execute the user's query."""

import sqlite3
from contextlib import closing
from pathlib import Path

from src.db import connect_readonly, validate_readonly

from .safety import CheckResult


def check_syntax(sql: str, *, db_path: str | Path | None = None) -> CheckResult:
    """Prepare guarded SQL using SQLite EXPLAIN against the selected schema."""
    try:
        guarded_sql = validate_readonly(sql)
        with closing(connect_readonly(db_path)) as connection:
            connection.execute("EXPLAIN " + guarded_sql).fetchall()
    except (ValueError, sqlite3.Error, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": None}
