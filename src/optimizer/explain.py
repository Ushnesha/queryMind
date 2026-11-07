"""Read-only SQLite plan inspection and plan signal parsing."""

import re
from contextlib import closing
from pathlib import Path
from typing import Any

from src.db import connect_readonly, validate_readonly

# Old SQLite writes "SCAN TABLE orders", new writes "SCAN orders".
_ACCESS = re.compile(r"^(SCAN|SEARCH)(?: TABLE)? (\S+)", re.IGNORECASE)


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


def plan_signals(plan: list[list[Any]]) -> dict[str, Any]:
    """Count plan signals. Each row is (id, parent, notused, detail)."""
    signals: dict[str, Any] = {
        "scans": 0, "searches": 0, "index_uses": 0, "temp_btrees": 0,
        "scanned_tables": [],
    }
    for row in plan:
        detail = str(row[3]).strip()
        upper = detail.upper()
        match = _ACCESS.match(detail)
        if match and match.group(2).upper() != "CONSTANT":  # CONSTANT ROW is free
            if match.group(1).upper() == "SCAN":
                signals["scans"] += 1
                signals["scanned_tables"].append(match.group(2))
            else:
                signals["searches"] += 1
        if "USING INDEX" in upper or "USING COVERING INDEX" in upper:
            signals["index_uses"] += 1
        if "TEMP B-TREE" in upper:
            signals["temp_btrees"] += 1
    return signals


def plan_improved(before: list[list[Any]], after: list[list[Any]]) -> bool:
    """True if after has fewer SCANs, SCAN became SEARCH, or fewer TEMP B-TREEs."""
    b, a = plan_signals(before), plan_signals(after)
    return (
        a["scans"] < b["scans"]
        or a["temp_btrees"] < b["temp_btrees"]
        or (a["searches"] > b["searches"] and a["scans"] <= b["scans"])
    )
