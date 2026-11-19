"""Key-aware DISTINCT preservation guard for the query optimizer (R5.2).

Prevents optimizer rewrites that remove DISTINCT unless uniqueness of the
projected output is provably guaranteed by schema keys on a single table.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import re
import sqlite3
from typing import Any

from src.db import connect_readonly


def _mask_strings_and_comments(sql: str) -> str:
    """Mask string literals ('...') and comments (-- or /* */) while preserving identifiers."""
    output: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        if sql.startswith("--", i):
            end = sql.find("\n", i + 2)
            i = n if end == -1 else end
            output.append(" ")
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                return sql
            i = end + 2
            output.append(" ")
        elif sql[i] == "'":
            i += 1
            output.append(" ")
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        output.append(" ")
                        continue
                    i += 1
                    break
                output.append(" ")
                i += 1
        else:
            output.append(sql[i])
            i += 1
    return "".join(output)


def has_distinct(sql: str) -> bool:
    """True if DISTINCT appears in the SQL outside string literals and comments."""
    masked = _mask_strings_and_comments(sql)
    return bool(re.search(r"\bDISTINCT\b", masked, re.IGNORECASE))


def parse_simple_single_table_select(sql: str) -> tuple[str, list[str]] | None:
    """Parse a simple single-table SELECT into (table_name, list_of_projected_columns).

    Returns None if the query contains joins, set operations, subqueries,
    CTEs, GROUP BY, aggregations, functions, or ambiguous constructs.
    Fails closed: only simple projections over a single base table are accepted.
    """
    masked = _mask_strings_and_comments(sql).strip()
    if masked.endswith(";"):
        masked = masked[:-1].strip()

    # Reject complex query structures that may multiply rows or obscure lineage
    if re.search(r"\b(JOIN|UNION|INTERSECT|EXCEPT|WITH|GROUP\s+BY)\b", masked, re.IGNORECASE):
        return None
    if re.search(r"\(\s*SELECT\b", masked, re.IGNORECASE):
        return None

    if not re.match(r"^SELECT\b", masked, re.IGNORECASE):
        return None

    # Split top-level SELECT and FROM
    parts = re.split(r"\bFROM\b", masked, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    select_part, from_part = parts[0], parts[1]

    # Projection expression
    proj_str = re.sub(r"^SELECT\s+", "", select_part, flags=re.IGNORECASE).strip()
    proj_str = re.sub(r"^(?:ALL\s+|DISTINCT\s+)", "", proj_str, flags=re.IGNORECASE).strip()

    # Split FROM part at WHERE / ORDER BY / LIMIT
    clauses = re.split(r"\b(?:WHERE|ORDER\s+BY|LIMIT)\b", from_part, maxsplit=1, flags=re.IGNORECASE)
    table_clause = clauses[0].strip()

    # Reject comma joins (e.g. FROM a, b) or subqueries in FROM
    if "," in table_clause or "(" in table_clause or ")" in table_clause:
        return None

    tokens = table_clause.split()
    if len(tokens) == 1:
        table_name = tokens[0].strip("\"`[]")
        alias: str | None = None
    elif len(tokens) == 2:
        table_name = tokens[0].strip("\"`[]")
        alias = tokens[1].strip("\"`[]")
    elif len(tokens) == 3 and tokens[1].upper() == "AS":
        table_name = tokens[0].strip("\"`[]")
        alias = tokens[2].strip("\"`[]")
    else:
        return None

    # Parse projected columns
    cols: list[str] = []
    for item in proj_str.split(","):
        item = item.strip()
        if not item or "(" in item or ")" in item or "*" in item:
            return None  # expressions, functions, or wildcard

        # Handle optional AS alias: col AS alias
        col_parts = re.split(r"\bAS\b", item, maxsplit=1, flags=re.IGNORECASE)
        col_expr = col_parts[0].strip()

        # Handle space alias without AS: col alias
        expr_tokens = col_expr.split()
        if not expr_tokens:
            return None
        col_expr = expr_tokens[0].strip()

        # Handle table or alias prefix: table.col or alias.col
        if "." in col_expr:
            pfx, cname = col_expr.split(".", maxsplit=1)
            pfx = pfx.strip("\"`[]")
            cname = cname.strip("\"`[]")
            valid_pfx = {table_name.lower()}
            if alias:
                valid_pfx.add(alias.lower())
            if pfx.lower() not in valid_pfx:
                return None
            cols.append(cname.lower())
        else:
            cols.append(col_expr.strip("\"`[]").lower())

    if not cols:
        return None

    return table_name, cols


def get_table_unique_keys(table_name: str, db_path: str | Path) -> list[set[str]]:
    """Return all sets of column names that form a PRIMARY KEY or declared UNIQUE constraint."""
    with closing(connect_readonly(db_path)) as connection:
        quoted = '"' + table_name.replace('"', '""') + '"'

        # Verify table exists
        table_row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) = lower(?)",
            (table_name,),
        ).fetchone()
        if not table_row:
            return []

        actual_table_name = table_row[0]
        actual_quoted = '"' + actual_table_name.replace('"', '""') + '"'

        # 1. Primary key columns
        pk_cols: set[str] = set()
        for row in connection.execute(f"PRAGMA table_info({actual_quoted})"):
            # row: (cid, name, type, notnull, dflt_value, pk)
            if row[5] > 0:
                pk_cols.add(str(row[1]).lower())

        unique_keys: list[set[str]] = []
        if pk_cols:
            unique_keys.append(pk_cols)

        # 2. Declared UNIQUE indexes
        for idx in connection.execute(f"PRAGMA index_list({actual_quoted})"):
            # idx: (seq, name, unique, origin, partial)
            is_unique = bool(idx[2])
            is_partial = bool(idx[4])
            if is_unique and not is_partial:
                idx_name = str(idx[1])
                idx_quoted = '"' + idx_name.replace('"', '""') + '"'
                idx_cols: set[str] = set()
                for term in connection.execute(f"PRAGMA index_info({idx_quoted})"):
                    # term: (seqno, cid, name)
                    if term[2] is not None:
                        idx_cols.add(str(term[2]).lower())
                if idx_cols:
                    unique_keys.append(idx_cols)

        return unique_keys


def check_distinct_guard(
    original_sql: str,
    candidate_sql: str,
    *,
    db_path: str | Path | None = None,
) -> tuple[bool, str]:
    """Verify whether removing DISTINCT is provably safe based on schema key metadata.

    Returns (True, reason) if:
    - original SQL did not use DISTINCT, OR
    - candidate SQL preserves DISTINCT, OR
    - candidate SQL is a simple single-table SELECT whose projected columns
      contain a declared PRIMARY KEY or UNIQUE constraint from that table.

    Returns (False, reason) if:
    - candidate removes DISTINCT without provable uniqueness guarantees.
    """
    orig_has_distinct = has_distinct(original_sql)
    cand_has_distinct = has_distinct(candidate_sql)

    # 1. If original didn't have DISTINCT, guard does not apply
    if not orig_has_distinct:
        return True, "original query does not use DISTINCT"

    # 2. If candidate preserves DISTINCT, guard passes
    if cand_has_distinct:
        return True, "candidate query preserves DISTINCT"

    # 3. Candidate removed DISTINCT: must prove uniqueness from schema constraints
    if db_path is None:
        return False, "unsafe DISTINCT removal: no database provided to verify key uniqueness"

    parsed = parse_simple_single_table_select(candidate_sql)
    if parsed is None:
        return (
            False,
            "unsafe DISTINCT removal: candidate contains joins, subqueries, expressions, or complex clauses",
        )

    table_name, projected_cols = parsed
    projected_set = set(projected_cols)

    try:
        unique_keys = get_table_unique_keys(table_name, db_path)
    except Exception as exc:
        return False, f"unsafe DISTINCT removal: failed to inspect table schema: {exc}"

    if not unique_keys:
        return False, f"unsafe DISTINCT removal: table '{table_name}' has no declared primary key or unique index"

    # Verify if projected columns contain any complete declared unique key
    for key_set in unique_keys:
        if key_set.issubset(projected_set):
            return True, f"safe DISTINCT removal: projection contains unique key {sorted(key_set)} for table '{table_name}'"

    return (
        False,
        f"unsafe DISTINCT removal: projected columns {sorted(projected_set)} do not contain a declared key of '{table_name}'",
    )
