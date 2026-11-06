"""Read-only SQLite introspection into a stable, versioned schema graph payload."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
from typing import Any

from src.db import connect_readonly


def build_schema_graph(
    db_path: str | Path | None = None, *, database_id: str | None = None
) -> dict[str, Any]:
    """Inspect columns, keys and indexes without modifying the SQLite database.

    A content fingerprint separates schema versions. Database IDs keep identical
    schemas belonging to different Spider databases in separate graph namespaces.
    """
    if db_path is None:
        from src.config import load_settings

        db_path = load_settings().database.path
    path = Path(db_path).expanduser().resolve()
    identifier = database_id if database_id is not None else path.stem
    if not identifier.strip():
        raise ValueError("database_id must not be empty.")
    tables: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    with closing(connect_readonly(path)) as connection:
        names = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        index_sql = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index'"
        ).fetchall())
        for name, table_sql in names:
            quoted = '"' + name.replace('"', '""') + '"'
            indexes: list[dict[str, Any]] = []
            for index in connection.execute(f"PRAGMA index_list({quoted})"):
                index_quoted = '"' + index[1].replace('"', '""') + '"'
                terms = connection.execute(f"PRAGMA index_info({index_quoted})").fetchall()
                indexes.append({
                    "name": index[1], "unique": bool(index[2]), "origin": index[3],
                    "partial": bool(index[4]), "sql": index_sql.get(index[1]),
                    "columns": [term[2] for term in terms if term[2] is not None],
                    "column_positions": [term[0] for term in terms if term[2] is not None],
                    "expression_positions": [term[0] for term in terms if term[2] is None],
                })
            tables.append({
                "name": name, "sql": table_sql,
                "columns": [
                    {"name": row[1], "type": row[2], "primary_key": bool(row[5]),
                     "not_null": bool(row[3]), "position": row[0], "pk_position": row[5],
                     "default": row[4]}
                    for row in connection.execute(f"PRAGMA table_info({quoted})")
                ],
                "indexes": sorted(indexes, key=lambda entry: entry["name"]),
            })
            relationships.extend(
                {"from_table": name, "from_column": row[3], "to_table": row[2],
                 "to_column": row[4], "constraint_id": row[0], "sequence": row[1],
                 "on_update": row[5], "on_delete": row[6], "match": row[7]}
                for row in connection.execute(f"PRAGMA foreign_key_list({quoted})")
            )
    by_name = {table["name"].casefold(): table for table in tables}
    for relationship in relationships:
        source = by_name[relationship["from_table"].casefold()]
        source_columns = {column["name"].casefold(): column["name"] for column in source["columns"]}
        relationship["from_column"] = source_columns.get(
            relationship["from_column"].casefold(), relationship["from_column"]
        )
        target = by_name.get(relationship["to_table"].casefold())
        if target is None:
            continue  # Preserve malformed/dangling SQLite metadata for diagnostics.
        relationship["to_table"] = target["name"]
        if relationship["to_column"] is None:
            primary_key = sorted(
                (column for column in target["columns"] if column["pk_position"]),
                key=lambda column: column["pk_position"],
            )
            sequence = relationship["sequence"]
            if sequence < len(primary_key):
                relationship["to_column"] = primary_key[sequence]["name"]
        else:
            target_columns = {column["name"].casefold(): column["name"] for column in target["columns"]}
            relationship["to_column"] = target_columns.get(
                relationship["to_column"].casefold(), relationship["to_column"]
            )
    relationships.sort(key=lambda item: (item["from_table"], item["constraint_id"], item["sequence"]))
    canonical = json.dumps({"tables": tables, "relationships": relationships}, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "status": "offline_payload_only", "database_id": identifier,
        "schema_fingerprint": fingerprint, "schema_id": f"{identifier}:{fingerprint}",
        "tables": tables, "relationships": relationships,
    }
