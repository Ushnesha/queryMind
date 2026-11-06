"""Deterministic Spider join-case selection using gold data only.

Gold annotations are evaluation metadata. They must never be passed to schema
retrievers or SQL providers.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def file_sha256(path: str | Path) -> str:
    """Return a stable content fingerprint without loading credentials."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _column(column_id: int, schema: dict[str, Any]) -> tuple[str, str]:
    table_id, name = schema["column_names_original"][column_id]
    return schema["table_names_original"][table_id], name


def _column_unit(value: Any) -> int | None:
    if (
        isinstance(value, list) and len(value) == 3
        and isinstance(value[0], int) and not isinstance(value[0], bool)
        and isinstance(value[1], int) and not isinstance(value[1], bool)
        and isinstance(value[2], bool)
    ):
        return value[1]
    return None


def _referenced_columns(value: Any) -> set[int]:
    column_id = _column_unit(value)
    if column_id is not None:
        return {column_id} if column_id > 0 else set()
    result: set[int] = set()
    if isinstance(value, dict):
        for nested in value.values():
            result.update(_referenced_columns(nested))
    elif isinstance(value, list):
        for nested in value:
            result.update(_referenced_columns(nested))
    return result


def _has_nested_sql(value: Any) -> bool:
    if isinstance(value, dict):
        return ("select" in value and "from" in value) or any(_has_nested_sql(item) for item in value.values())
    return isinstance(value, list) and any(_has_nested_sql(item) for item in value)


def _edge(source: int, target: int, schema: dict[str, Any]) -> dict[str, str]:
    from_table, from_column = _column(source, schema)
    to_table, to_column = _column(target, schema)
    return {
        "from_table": from_table, "from_column": from_column,
        "to_table": to_table, "to_column": to_column,
    }


def annotate_case(source_index: int, question: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
    """Extract connected explicit FK joins from a simple Spider SQL AST.

    Selection excludes nested/set-operation queries and non-FK-only join paths
    to keep this small retrieval experiment's gold definition unambiguous.
    Spider comparison operator 2 is equality; join orientation is taken from
    tables.json's declared foreign-key pair, rather than SQL alias spelling.
    """
    ast = question["sql"]
    if any(_has_nested_sql(value) for value in ast.values()):
        return None
    units = ast["from"]["table_units"]
    if not units or any(unit[0] != "table_unit" for unit in units):
        return None
    table_ids = {unit[1] for unit in units}
    if len(table_ids) < 2:
        return None
    foreign_keys = {frozenset((source, target)): (source, target) for source, target in schema["foreign_keys"]}
    joins: dict[tuple[int, int], dict[str, str]] = {}
    for condition in ast["from"].get("conds", []):
        if not isinstance(condition, list) or len(condition) != 5:
            continue
        negated, operator, value_unit, right, _ = condition
        if negated or operator != 2 or value_unit[0] != 0:
            continue
        left_id = _column_unit(value_unit[1])
        right_id = _column_unit(right)
        if left_id is None or right_id is None:
            continue
        pair = foreign_keys.get(frozenset((left_id, right_id)))
        if pair:
            joins[pair] = _edge(*pair, schema)
    tables = {schema["table_names_original"][index] for index in table_ids}
    adjacency: dict[str, set[str]] = {table: set() for table in tables}
    for edge in joins.values():
        if edge["from_table"] in tables and edge["to_table"] in tables:
            adjacency[edge["from_table"]].add(edge["to_table"])
            adjacency[edge["to_table"]].add(edge["from_table"])
    visited: set[str] = set()
    pending = [next(iter(sorted(tables)))]
    while pending:
        current = pending.pop()
        if current not in visited:
            visited.add(current)
            pending.extend(adjacency[current] - visited)
    if visited != tables:
        return None
    aggregation = bool(ast.get("groupBy") or ast.get("having")) or any(
        selected[0] != 0 for selected in ast["select"][1]
    )
    return {
        "id": f"spider_dev_{source_index:04d}",
        "source_index": source_index,
        "db_id": question["db_id"],
        "question": question["question"],
        "reference_sql": question["query"],
        "required_tables": sorted(tables),
        "required_columns": sorted(".".join(_column(index, schema)) for index in _referenced_columns(ast)),
        "required_joins": [joins[pair] for pair in sorted(joins)],
        "schema_table_count": len(schema["table_names_original"]),
        "has_aggregation": aggregation,
        "requires_bridge": len(tables) >= 3 and any(len(neighbors) >= 2 for neighbors in adjacency.values()),
        "gold_ast_sha256": hashlib.sha256(json.dumps(ast, sort_keys=True).encode()).hexdigest(),
    }


def select_spider_cases(dataset_root: str | Path, count: int = 10) -> dict[str, Any]:
    """Select two cases per database before any retrieval or generation runs.

    Databases are ordered by descending schema size then database ID; eligible
    databases need at least two distinct queries, one aggregation case and one
    3+ table bridge. Within each database, take the largest-table join (prefer
    aggregation on a tie), then the earliest distinct query that supplies
    aggregation when needed. This deliberately favors larger schemas.
    """
    if count < 2 or count % 2:
        raise ValueError("count must be a positive even number of at least two")
    root = Path(dataset_root)
    questions = json.loads((root / "dev.json").read_text(encoding="utf-8"))
    schemas = {schema["db_id"]: schema for schema in json.loads((root / "tables.json").read_text(encoding="utf-8"))}
    by_database: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    for index, question in enumerate(questions):
        case = annotate_case(index, question, schemas[question["db_id"]])
        normalized = " ".join(question["query"].lower().split())
        if case is not None and normalized not in seen[question["db_id"]]:
            by_database[question["db_id"]].append(case)
            seen[question["db_id"]].add(normalized)
    eligible = [
        db_id for db_id, cases in by_database.items()
        if len(cases) >= 2 and any(case["requires_bridge"] for case in cases)
        and any(case["has_aggregation"] for case in cases)
    ]
    eligible.sort(key=lambda name: (-len(schemas[name]["table_names_original"]), name.casefold()))
    selected: list[dict[str, Any]] = []
    for db_id in eligible[: count // 2]:
        cases = sorted(by_database[db_id], key=lambda case: (-len(case["required_tables"]), -case["has_aggregation"], case["source_index"]))
        first = next(case for case in cases if case["requires_bridge"])
        remaining = [case for case in cases if case["id"] != first["id"]]
        second = min(
            (case for case in remaining if first["has_aggregation"] or case["has_aggregation"]),
            key=lambda case: case["source_index"],
        )
        selected.extend((first, second))
    if len(selected) != count:
        raise ValueError(f"Only {len(selected)} eligible cases available for requested count={count}")
    return {
        "format_version": 1,
        "dataset": "Spider development split",
        "source_index_base": 0,
        "source_question_count": len(questions),
        "source_files": {name: {"sha256": file_sha256(root / name)} for name in ("dev.json", "tables.json")},
        "selection": {
            "method": "gold_only_v1",
            "case_count": count,
            "cases_per_database": 2,
            "database_order": "descending schema table count, then case-insensitive database ID",
            "criteria": "connected explicit declared-FK equijoins; no nested/set queries; each database supplies a 3+ table bridge and aggregation; SQL-deduplicated",
            "retrieval_or_generation_outputs_used": False,
        },
        "cases": selected,
    }


def load_cases(path: str | Path) -> dict[str, Any]:
    """Read the persisted, reviewable gold-only experiment manifest."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list) or not manifest["cases"]:
        raise ValueError("Spider case manifest must contain a nonempty 'cases' list")
    return manifest


def validate_cases(manifest: dict[str, Any], dataset_root: str | Path) -> None:
    """Fail on changed sources or stale gold annotations before benchmarking."""
    root = Path(dataset_root)
    for filename, source in manifest["source_files"].items():
        if filename not in {"dev.json", "tables.json"} or file_sha256(root / filename) != source["sha256"]:
            raise ValueError(f"Spider source fingerprint differs: {filename}")
    questions = json.loads((root / "dev.json").read_text(encoding="utf-8"))
    schemas = {schema["db_id"]: schema for schema in json.loads((root / "tables.json").read_text(encoding="utf-8"))}
    for case in manifest["cases"]:
        original = questions[case["source_index"]]
        if annotate_case(case["source_index"], original, schemas[original["db_id"]]) != case:
            raise ValueError(f"Spider case annotations differ from source: {case['id']}")
