"""Read-only SQLite plan inspection."""

from contextlib import closing
from pathlib import Path
from typing import Any

from src.db import connect_readonly, validate_readonly


def explain_query_plan(
    sql: str, *, db_path: str | Path | None = None
) -> list[list[Any]]:
    """Return JSON-serializable EXPLAIN QUERY PLAN rows for guarded SQL."""
    guarded_sql = validate_readonly(sql)
    with closing(connect_readonly(db_path)) as connection:
        return [
            list(row)
            for row in connection.execute("EXPLAIN QUERY PLAN " + guarded_sql)
        ]
