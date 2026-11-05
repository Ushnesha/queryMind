"""Shared, JSON-serializable contract; coordinate changes with the integration owner."""

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """Data exchanged by all nodes; no connections, providers, or framework objects."""

    question: str
    schema_mode: str
    schema_context: str
    sql: str
    sql_history: list[str]
    syntax_ok: bool
    syntax_error: str
    safety_ok: bool
    semantic_ok: bool
    semantic_reason: str
    answerable: bool
    missing_fields: list[str]
    assumptions: list[str]
    original_sql: str
    optimized_sql: str
    optimization_applied: bool
    original_plan: list[Any]
    optimized_plan: list[Any]
    rows: list[Any]
    columns: list[str]
    result_ok: bool
    result_warnings: list[str]
    final_answer: str
    repair_count: int
    optimizer_count: int
    trace: list[dict[str, Any]]
    metrics: dict[str, Any]
    status: Literal["success", "refused", "error"]
    error: str
