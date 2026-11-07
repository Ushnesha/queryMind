"""Explicit Neo4j persistence and native join-path queries for schema metadata.

The SDK is optional and imported only when a caller explicitly opens a driver.
All values are Cypher parameters; SQLite names never become Cypher syntax.
"""

from __future__ import annotations

import json
import os
from typing import Any


def open_driver_from_env() -> Any:
    """Create a caller-owned driver using already configured environment values.

    No dotenv file is read here. CLI entry points may load it explicitly. Driver
    creation is lazy; the first graph operation makes the service connection.
    """
    required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
    if any(not os.environ.get(name, "").strip() for name in required):
        raise ValueError("Set NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD to enable Neo4j.")
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError("Neo4j support requires pip install -r requirements-schema.txt") from exc
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        connection_timeout=5.0, connection_acquisition_timeout=10.0,
        max_transaction_retry_time=10.0,
    )


def _session(driver: Any, database: str | None) -> Any:
    name = database or os.environ.get("NEO4J_DATABASE")
    return driver.session(**({"database": name} if name else {}))


def _key(*parts: str) -> str:
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def upload_schema_graph(
    payload: dict[str, Any], *, driver: Any, database: str | None = None
) -> dict[str, Any]:
    """Idempotently MERGE one schema version in one managed write transaction.

    Existing schema versions and unrelated graphs remain intact. Upload refuses
    dangling FK definitions instead of silently dropping relationships.
    """
    schema_id, database_id = payload["schema_id"], payload["database_id"]
    tables, columns, indexes, references, index_columns = [], [], [], [], []
    known_columns: set[tuple[str, str]] = set()
    for table in payload["tables"]:
        table_name = table["name"]
        tables.append({"name": table_name, "sql": table.get("sql"), "key": _key(schema_id, table_name)})
        for column in table["columns"]:
            known_columns.add((table_name, column["name"]))
            columns.append({"table_name": table_name, "name": column["name"],
                            "properties": {**column, "key": _key(schema_id, table_name, column["name"])}})
        for index in table.get("indexes", []):
            indexes.append({"table_name": table_name, "name": index["name"],
                            "properties": {**index, "key": _key(schema_id, table_name, index["name"])}})
            positions = index.get("column_positions", list(range(len(index["columns"]))))
            index_columns.extend({"table_name": table_name, "index_name": index["name"],
                                  "column_name": name, "position": position}
                                 for name, position in zip(index["columns"], positions))
    for relationship in payload["relationships"]:
        if (relationship["from_table"], relationship["from_column"]) not in known_columns or (
            relationship["to_table"], relationship["to_column"]
        ) not in known_columns:
            raise ValueError("Cannot upload an unresolved foreign-key column reference.")
        references.append(dict(relationship))

    def write(tx: Any) -> None:
        common = {"schema_id": schema_id, "database_id": database_id}
        tx.run(
            "MERGE (s:Schema {schema_id: $schema_id}) "
            "SET s.database_id = $database_id, s.schema_fingerprint = $fingerprint",
            **common, fingerprint=payload["schema_fingerprint"],
        ).consume()
        tx.run(
            "MATCH (s:Schema {schema_id: $schema_id}) UNWIND $tables AS row "
            "MERGE (t:Table {schema_id: $schema_id, name: row.name}) "
            "SET t.database_id = $database_id, t.key = row.key, t.sql = row.sql "
            "MERGE (s)-[:HAS_TABLE]->(t)", **common, tables=tables,
        ).consume()
        tx.run(
            "UNWIND $columns AS row "
            "MATCH (t:Table {schema_id: $schema_id, name: row.table_name}) "
            "MERGE (c:Column {schema_id: $schema_id, table_name: row.table_name, name: row.name}) "
            "SET c += row.properties, c.database_id = $database_id "
            "MERGE (t)-[:HAS_COLUMN]->(c)", **common, columns=columns,
        ).consume()
        tx.run(
            "UNWIND $indexes AS row "
            "MATCH (t:Table {schema_id: $schema_id, name: row.table_name}) "
            "MERGE (i:Index {schema_id: $schema_id, table_name: row.table_name, name: row.name}) "
            "SET i += row.properties, i.database_id = $database_id "
            "MERGE (t)-[:HAS_INDEX]->(i)", **common, indexes=indexes,
        ).consume()
        tx.run(
            "UNWIND $references AS row "
            "MATCH (source:Column {schema_id: $schema_id, table_name: row.from_table, name: row.from_column}) "
            "MATCH (target:Column {schema_id: $schema_id, table_name: row.to_table, name: row.to_column}) "
            "MERGE (source)-[r:REFERENCES {constraint_id: row.constraint_id, sequence: row.sequence}]->(target) "
            "SET r.on_update = row.on_update, r.on_delete = row.on_delete, r.match = row.match",
            **common, references=references,
        ).consume()
        tx.run(
            "UNWIND $index_columns AS row "
            "MATCH (i:Index {schema_id: $schema_id, table_name: row.table_name, name: row.index_name}) "
            "MATCH (c:Column {schema_id: $schema_id, table_name: row.table_name, name: row.column_name}) "
            "MERGE (i)-[:INDEXES {position: row.position}]->(c)",
            **common, index_columns=index_columns,
        ).consume()

    with _session(driver, database) as session:
        session.execute_write(write)
    return {"status": "uploaded", "schema_id": schema_id, "tables": len(tables),
            "columns": len(columns), "indexes": len(indexes), "references": len(references)}


def load_schema_graph(
    *, driver: Any, schema_id: str, database: str | None = None
) -> dict[str, Any]:
    """Read the stored node/edge metadata back into the shared payload shape."""
    def read(tx: Any) -> dict[str, Any]:
        records = list(tx.run(
            "MATCH (s:Schema {schema_id: $schema_id}) RETURN properties(s) AS schema",
            schema_id=schema_id,
        ))
        if not records:
            raise LookupError("The requested schema has not been uploaded to Neo4j.")
        metadata = dict(records[0]["schema"])
        tables = {record["table"]["name"]: {
            "name": record["table"]["name"], "sql": record["table"].get("sql"),
            "columns": [], "indexes": [],
        } for record in tx.run(
            "MATCH (t:Table {schema_id: $schema_id}) RETURN properties(t) AS table ORDER BY t.name",
            schema_id=schema_id,
        )}
        for record in tx.run(
            "MATCH (:Table {schema_id: $schema_id})-[:HAS_COLUMN]->(c:Column {schema_id: $schema_id}) "
            "RETURN properties(c) AS column ORDER BY c.table_name, c.position",
            schema_id=schema_id,
        ):
            column = dict(record["column"])
            table_name = column.pop("table_name")
            for key in ("schema_id", "database_id", "key"):
                column.pop(key, None)
            column.setdefault("default", None)
            tables[table_name]["columns"].append(column)
        for record in tx.run(
            "MATCH (:Table {schema_id: $schema_id})-[:HAS_INDEX]->(i:Index {schema_id: $schema_id}) "
            "RETURN properties(i) AS index ORDER BY i.table_name, i.name",
            schema_id=schema_id,
        ):
            index = dict(record["index"])
            table_name = index.pop("table_name")
            for key in ("schema_id", "database_id", "key"):
                index.pop(key, None)
            index.setdefault("sql", None)
            tables[table_name]["indexes"].append(index)
        relationships = []
        for record in tx.run(
            "MATCH (source:Column {schema_id: $schema_id})-[r:REFERENCES]->(target:Column {schema_id: $schema_id}) "
            "RETURN source.table_name AS from_table, source.name AS from_column, "
            "target.table_name AS to_table, target.name AS to_column, properties(r) AS metadata "
            "ORDER BY from_table, r.constraint_id, r.sequence", schema_id=schema_id,
        ):
            relationships.append({
                "from_table": record["from_table"], "from_column": record["from_column"],
                "to_table": record["to_table"], "to_column": record["to_column"],
                **dict(record["metadata"]),
            })
        return {"status": "loaded_from_neo4j", "schema_id": schema_id,
                "database_id": metadata["database_id"], "schema_fingerprint": metadata["schema_fingerprint"],
                "tables": list(tables.values()), "relationships": relationships}

    with _session(driver, database) as session:
        return session.execute_read(read)


def expand_join_paths(
    *, driver: Any, schema_id: str, table_names: list[str], database: str | None = None
) -> list[str]:
    """Expand seed tables through Neo4j shortest paths, preserving disconnected seeds.

    Paths use at most 32 HAS_COLUMN/REFERENCES edges. A full table-to-table FK
    traversal costs three edges; shared-column chains can cost fewer. Column
    owners are included even when a shortest path bypasses their Table node.
    All nodes must belong to this schema version.
    """
    seeds = sorted(set(table_names))
    if not seeds:
        return []

    def read(tx: Any) -> list[str]:
        records = tx.run(
            "UNWIND $table_names AS left_name UNWIND $table_names AS right_name "
            "WITH left_name, right_name WHERE left_name < right_name "
            "MATCH (source:Table {schema_id: $schema_id, name: left_name}) "
            "MATCH (target:Table {schema_id: $schema_id, name: right_name}) "
            "MATCH path = shortestPath((source)-[:HAS_COLUMN|REFERENCES*1..32]-(target)) "
            "WHERE all(node IN nodes(path) WHERE node.schema_id = $schema_id) "
            "UNWIND nodes(path) AS node "
            "WITH CASE WHEN node:Table THEN node.name ELSE node.table_name END AS table_name "
            "RETURN DISTINCT table_name ORDER BY table_name",
            schema_id=schema_id, table_names=seeds,
        )
        return sorted(set(seeds).union(record["table_name"] for record in records))

    with _session(driver, database) as session:
        return session.execute_read(read)
