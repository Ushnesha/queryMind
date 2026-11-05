"""Offline schema graph payload construction; uploading to Neo4j is deferred."""

from contextlib import closing
from pathlib import Path
from typing import Any

from src.db import connect_readonly


def build_schema_graph(db_path: str | Path | None = None) -> dict[str, Any]:
    """Create JSON-compatible table/column/foreign-key metadata, without writes."""
    tables: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    with closing(connect_readonly(db_path)) as connection:
        names = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (name,) in names:
            quoted = '"' + name.replace('"', '""') + '"'
            tables.append({
                "name": name,
                "columns": [
                    {"name": row[1], "type": row[2], "primary_key": bool(row[5])}
                    for row in connection.execute(f"PRAGMA table_info({quoted})")
                ],
            })
            relationships.extend(
                {"from_table": name, "from_column": row[3], "to_table": row[2], "to_column": row[4]}
                for row in connection.execute(f"PRAGMA foreign_key_list({quoted})")
            )
    # TODO(feature/schema-graph): upload this payload with an optional Neo4j driver.
    return {"status": "offline_payload_only", "tables": tables, "relationships": relationships}
