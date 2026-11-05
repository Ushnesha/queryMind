"""Deterministic response formatting; language generation belongs to future work."""

from src.state import AgentState


def generate_response(state: AgentState) -> str:
    """Describe execution without claiming that placeholder checks prove correctness."""
    if state.get("status") == "error":
        return "QueryMind could not complete the query: " + state.get("error", "Unknown error")
    if not state.get("answerable", True):
        reason = state.get("semantic_reason") or state.get("error") or "The requested information is unavailable."
        missing = state.get("missing_fields", [])
        return "I cannot answer this question. " + reason + (" Missing fields: " + ", ".join(missing) if missing else "")
    rows, columns = state.get("rows", []), state.get("columns", [])
    if not rows:
        return "The query returned no matching rows. See the SQL and verification details."
    if len(rows) == 1 and len(columns) == 1:
        return f"The query returned {columns[0]} = {rows[0][0]}. See verification details."
    # TODO(feature/eval-ui): replace with a grounded plain-English response generator.
    return f"The query returned {len(rows)} row(s). See the result table and verification details."
