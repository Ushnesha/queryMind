"""Thin Streamlit entry point using QueryMind's public orchestration contract."""

from __future__ import annotations

import streamlit as st

from src.orchestrator import run_querymind
from src.state import AgentState


def main() -> None:
    """Render the offline starter UI; database creation remains an explicit step."""
    st.set_page_config(page_title="QueryMind", page_icon="🔎", layout="wide")
    st.title("QueryMind")
    st.caption(
        "Milestone 2 starter · offline mock SQL generation · "
        "semantic verification and optimization are placeholders"
    )
    question = st.text_input(
        "Business question",
        placeholder="Who are the top 3 customers by total spending?",
    )
    if not st.button("Ask QueryMind", type="primary"):
        return
    if not question.strip():
        st.warning("Enter a business question.")
        return

    try:
        with st.spinner("Running QueryMind…"):
            state = run_querymind(question, schema_mode="flat")
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        st.error(f"QueryMind could not run: {exc}")
        st.info("Create the local demonstration database with `make seed`.")
        return

    st.subheader("Answer")
    st.write(state.get("final_answer") or "No answer was produced.")
    if state.get("error"):
        st.error(str(state["error"]))

    st.subheader("Results")
    columns = state.get("columns", [])
    rows = state.get("rows", [])
    if columns:
        # Passing records avoids importing data-layer implementation details.
        st.dataframe(
            [dict(zip(columns, row)) for row in rows],
            use_container_width=True,
        )
    else:
        st.info("No result table is available.")

    st.subheader("SQL")
    sql = state.get("optimized_sql") if state.get("optimization_applied") else state.get("sql")
    if sql:
        st.code(sql, language="sql")
    else:
        st.write("No SQL was generated.")

    st.subheader("Assumptions")
    assumptions = state.get("assumptions", [])
    st.write("\n".join(f"- {item}" for item in assumptions) if assumptions else "None recorded.")
    missing_fields = state.get("missing_fields", [])
    if missing_fields:
        st.warning("Missing fields: " + ", ".join(missing_fields))

    st.subheader("Verification")
    st.write(f"Run status: {state.get('status', 'unknown')}")
    for title, node, field in (
        ("Read-only safety", "safety_verifier", "safety_ok"),
        ("Syntax", "syntax_verifier", "syntax_ok"),
        ("Semantics", "semantic_verifier", "semantic_ok"),
        ("Results", "result_verifier", "result_ok"),
    ):
        st.write(f"{title}: {_verification_label(state, node, field)}")
    st.caption("Semantic and result checks are starter checks; they do not establish answer correctness.")
    if state.get("semantic_reason"):
        st.write(state["semantic_reason"])
    for warning in state.get("result_warnings", []):
        st.warning(str(warning))
    for event in state.get("trace", []):
        if event.get("status") in {"warning", "placeholder", "skipped", "fallback"}:
            st.caption(f"{event.get('node', 'component')}: {event.get('reason', event['status'])}")

    with st.expander("Agent execution trace"):
        st.json(state.get("trace", []))


def _verification_label(state: AgentState, node: str, field: str) -> str:
    """Keep disabled and placeholder checks distinct from validated results."""
    events = [event for event in state.get("trace", []) if event.get("node") == node]
    if not events:
        return "not run"
    status = events[-1].get("status")
    if status == "skipped":
        return "disabled"
    if status == "placeholder":
        return "starter checks only"
    if status in {"fail", "error"}:
        return "failed"
    value = state.get(field)
    return "passed" if value is True else "failed" if value is False else "not run"


if __name__ == "__main__":
    main()
