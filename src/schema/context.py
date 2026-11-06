"""Render identical schema facts for flat and selected graph contexts."""

from time import perf_counter
import re
from typing import Any, Iterable

from src.schema.interface import RetrievalResult


def quote_identifier(name: str) -> str:
    """Keep simple names readable and quote complex or common reserved names."""
    reserved = {"select", "from", "where", "group", "order", "table", "index", "join", "limit", "with", "as", "on", "values"}
    if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) and name.lower() not in reserved:
        return name
    return '"' + name.replace('"', '""') + '"'


def render_schema(payload: dict[str, Any], table_names: Iterable[str]) -> str:
    """Render selected tables, complete columns, internal FKs and index metadata."""
    selected = set(table_names)
    relationships = payload["relationships"]
    sections: list[str] = []
    for table in payload["tables"]:
        name = table["name"]
        if name not in selected:
            continue
        columns = sorted(table["columns"], key=lambda column: column.get("position", 0))
        primary = sorted(
            (column for column in columns if column["primary_key"]),
            key=lambda column: column.get("pk_position", column.get("position", 0)),
        )
        definitions = [
            "  " + quote_identifier(column["name"]) + " " + (column["type"] or "ANY")
            + (" PRIMARY KEY" if column["primary_key"] and len(primary) == 1 else "")
            + (" NOT NULL" if column.get("not_null") else "")
            for column in columns
        ]
        if len(primary) > 1:
            definitions.append("  PRIMARY KEY (" + ", ".join(quote_identifier(c["name"]) for c in primary) + ")")
        groups: dict[tuple[str, Any], list[dict[str, Any]]] = {}
        for edge in relationships:
            if edge["from_table"] == name and edge["to_table"] in selected:
                key = (edge["to_table"], edge.get("constraint_id", edge["from_column"]))
                groups.setdefault(key, []).append(edge)
        for edges in groups.values():
            ordered = sorted(edges, key=lambda edge: edge.get("sequence", 0))
            definitions.append(
                "  FOREIGN KEY (" + ", ".join(quote_identifier(e["from_column"]) for e in ordered)
                + ") REFERENCES " + quote_identifier(ordered[0]["to_table"]) + "("
                + ", ".join(quote_identifier(e["to_column"]) for e in ordered) + ")"
            )
        sections.append("TABLE " + quote_identifier(name) + " (\n" + ",\n".join(definitions) + "\n)")
        for index in table.get("indexes", []):
            if index.get("sql"):
                # PRAGMA index_info omits expression text, sort order and the
                # partial-index predicate. SQLite's stored DDL preserves them.
                sections.append(index["sql"].strip().rstrip(";"))
                continue
            positions = index.get("column_positions", list(range(len(index["columns"]))))
            slots = {position: quote_identifier(column) for position, column in zip(positions, index["columns"])}
            slots.update({position: "<expression>" for position in index.get("expression_positions", [])})
            index_columns = [slots[position] for position in sorted(slots)]
            sections.append(
                ("UNIQUE " if index["unique"] else "") + "INDEX " + quote_identifier(index["name"])
                + " ON " + quote_identifier(name) + " (" + ", ".join(index_columns) + ")"
                + (" [partial]" if index.get("partial") else "")
            )
    return "\n\n".join(sections)


def retrieval_result(
    payload: dict[str, Any], table_names: Iterable[str], *, backend: str,
    started: float, seed_tables: Iterable[str] = (), fallback_reason: str = "",
) -> RetrievalResult:
    """Create context and metadata with one shared rendering policy for both arms."""
    selected = set(table_names)
    tables = [table for table in payload["tables"] if table["name"] in selected]
    context = render_schema(payload, selected)
    return RetrievalResult(
        context=context,
        tables=[table["name"] for table in tables],
        columns=[f"{table['name']}.{column['name']}" for table in tables for column in table["columns"]],
        relationships=[dict(edge) for edge in payload["relationships"]
                       if edge["from_table"] in selected and edge["to_table"] in selected],
        backend=backend, latency_ms=(perf_counter() - started) * 1000,
        schema_id=payload["schema_id"], seed_tables=list(seed_tables), fallback_reason=fallback_reason,
    )
