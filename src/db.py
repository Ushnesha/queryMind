"""Shared SQLite access: schema discovery and read-only query execution."""

from __future__ import annotations

from contextlib import closing
import math
from pathlib import Path
import re
import sqlite3
from time import perf_counter
from typing import Any, TypedDict


class ExecutionResult(TypedDict):
    """JSON-compatible result returned by the public executor."""

    rows: list[list[Any]]
    columns: list[str]
    execution_time_ms: float


def _mask_literals_and_comments(sql: str) -> str:
    """Hide quoted values/identifiers and comments before checking SQL tokens."""
    output: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = len(sql) if end == -1 else end
            output.append(" ")
        elif sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                raise ValueError("Unterminated SQL comment.")
            index = end + 2
            output.append(" ")
        elif char in "'\"`[":
            closing_char = "]" if char == "[" else char
            index += 1
            while index < len(sql):
                if sql[index] == closing_char:
                    if char != "[" and index + 1 < len(sql) and sql[index + 1] == closing_char:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise ValueError("Unterminated SQL string or identifier.")
            output.append(" quoted ")
        else:
            output.append(char)
            index += 1
    return "".join(output)


def validate_readonly(sql: str) -> str:
    """Accept one SELECT/CTE statement or raise ValueError before execution.

    The connection's SQLite authorizer remains the authoritative second gate;
    this small lexical guard is deliberately not a full SQL parser.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL must be a non-empty string.")
    masked = _mask_literals_and_comments(sql).strip()
    if masked.endswith(";"):
        masked = masked[:-1].rstrip()
    if ";" in masked:
        raise ValueError("Only one SQL statement is allowed.")
    if not re.match(r"^(SELECT|WITH)\b", masked, re.IGNORECASE):
        raise ValueError("Only read-only SELECT or WITH queries are allowed.")
    if re.search(
        r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|ATTACH|DETACH|"
        r"VACUUM|REINDEX|ANALYZE|PRAGMA|BEGIN|COMMIT|ROLLBACK)\b",
        masked,
        re.IGNORECASE,
    ):
        raise ValueError("SQL contains an operation outside the read-only contract.")
    if re.search(r"\b(load_extension|readfile|writefile)\s*\(", masked, re.IGNORECASE):
        raise ValueError("File and extension functions are forbidden.")
    return sql.strip()


def _readonly_authorizer(
    action: int,
    argument_one: str | None,
    argument_two: str | None,
    database_name: str | None,
    trigger_name: str | None,
) -> int:
    """Restrict SQLite itself, including callers that bypass the lexical guard."""
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        function = (argument_two or argument_one or "").lower()
        return sqlite3.SQLITE_DENY if function in {"load_extension", "readfile", "writefile"} else sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and (argument_one or "").lower() in {
        "table_info", "foreign_key_list", "index_list", "index_info",
    }:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def connect_readonly(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open an existing database with mode=ro, query_only and an authorizer.

    Callers own the connection and must close it, e.g. contextlib.closing().
    This function never creates or seeds a missing database.
    """
    if db_path is None:
        from src.config import load_settings

        db_path = load_settings().database.path
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}. Run make seed first.")
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.set_authorizer(_readonly_authorizer)
    return connection


def introspect_schema(db_path: str | Path | None = None) -> str:
    """Render SQLite tables, columns and foreign keys as readable schema text."""
    with closing(connect_readonly(db_path)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        sections: list[str] = []
        for (table,) in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
            definitions = [
                f"  {name} {kind or 'ANY'}" + (" PRIMARY KEY" if primary else "")
                + (" NOT NULL" if not_null else "")
                for _, name, kind, not_null, _, primary in columns
            ]
            for foreign_key in connection.execute(f"PRAGMA foreign_key_list({quoted})"):
                definitions.append(
                    f"  FOREIGN KEY ({foreign_key[3]}) REFERENCES {foreign_key[2]}({foreign_key[4]})"
                )
            sections.append(f"TABLE {table} (\n" + ",\n".join(definitions) + "\n)")
    return "\n\n".join(sections)


def execute_sql(sql: str, *, db_path: str | Path | None = None) -> ExecutionResult:
    """Execute one guarded read-only query and return JSON-compatible results.

    BLOB and non-finite float cells use tagged objects so strict JSON works and
    result comparison cannot confuse a BLOB with an ordinary hex text value.
    """
    guarded_sql = validate_readonly(sql)
    started = perf_counter()
    with closing(connect_readonly(db_path)) as connection:
        cursor = connection.execute(guarded_sql)
        columns = [description[0] for description in cursor.description or []]
        rows = [[_json_cell(value) for value in row] for row in cursor.fetchall()]
    return {
        "rows": rows,
        "columns": columns,
        "execution_time_ms": (perf_counter() - started) * 1000,
    }


def _json_cell(value: Any) -> Any:
    """Preserve exceptional SQLite cell types through strict JSON encoding."""
    if isinstance(value, bytes):
        return {"type": "blob", "hex": value.hex()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"type": "nonfinite_float", "value": str(value)}
    return value
