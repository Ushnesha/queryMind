"""Streamlit presentation of QueryMind's public orchestration state."""

from __future__ import annotations

import streamlit as st

from src.orchestrator import run_querymind
from src.state import AgentState


def main() -> None:
    """Ask a question and retain its result across Streamlit reruns."""
    st.set_page_config(page_title="QueryMind", page_icon="🔎", layout="wide")
    st.title("QueryMind")
    st.caption("Ask a business question and inspect the answer, SQL, and verification.")
    question = st.text_input(
        "Ask your database",
        placeholder="Who are the top 3 customers by total spending?",
        key="querymind_question",
    )
    if st.button("Ask QueryMind", type="primary"):
        if not question.strip():
            st.warning("Enter a business question.")
            return
        try:
            with st.spinner("Running QueryMind…"):
                state = run_querymind(question.strip(), schema_mode="flat")
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            st.session_state.pop("querymind_result", None)
            st.error(f"QueryMind could not run: {exc}")
            return
        st.session_state["querymind_result"] = state

    state = st.session_state.get("querymind_result")
    if state is not None:
        _render_result(state)


def _render_result(state: AgentState) -> None:
    """Display the shared state without generating answers or running checks."""
    if state.get("question"):
        st.caption("Question: " + state["question"])
    st.subheader("Answer")
    refused = state.get("status") == "refused" or state.get("answerable") is False
    if refused:
        st.warning("QueryMind cannot reliably answer this question.")
        missing = state.get("missing_fields", [])
        if missing:
            title = "Missing field" if len(missing) == 1 else "Missing fields"
            st.write(f"{title}: " + ", ".join(missing))
        reason = state.get("semantic_reason") or state.get("error") or state.get("final_answer")
        st.write("Reason: " + (reason or "The pipeline did not provide a reliable answer."))
    else:
        st.write(state.get("final_answer") or "No answer was produced.")
    if state.get("error"):
        st.error(str(state["error"]))

    st.subheader("Result")
    columns, rows = state.get("columns", []), state.get("rows", [])
    if columns:
        # Numeric source columns retain positional data, including duplicate SQL
        # column labels; column_config supplies the labels for presentation.
        st.dataframe(
            {str(index): [row[index] for row in rows] for index in range(len(columns))},
            column_config={str(index): name for index, name in enumerate(columns)},
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No result table is available.")

    st.subheader("Generated SQL")
    sql = state.get("optimized_sql") or state.get("sql")
    if sql:
        st.code(sql, language="sql")
    else:
        st.write("No SQL was generated.")

    st.subheader("Assumptions")
    assumptions = state.get("assumptions", [])
    st.write("\n".join(f"- {item}" for item in assumptions) if assumptions else "None")

    st.subheader("Verification")
    st.caption(f"Run status: {state.get('status', 'unknown')}")
    for title, node, field in (
        ("SQL safe", "safety_verifier", "safety_ok"),
        ("Syntax valid", "syntax_verifier", "syntax_ok"),
        ("Semantic verification", "semantic_verifier", "semantic_ok"),
        ("Result sanity", "result_verifier", "result_ok"),
    ):
        label = _verification_label(state, node, field)
        st.write(f"✓ {title}" if label == "passed" else f"— {title}: {label}")
    optimizer = _optimizer_label(state)
    st.write("✓ Optimizer preserved result" if optimizer == "passed" else f"— Optimizer: {optimizer}")
    if not refused and state.get("semantic_reason"):
        st.caption(state["semantic_reason"])
    for warning in state.get("result_warnings", []):
        st.warning(str(warning))
    for event in state.get("trace", []):
        if event.get("status") in {"warning", "placeholder", "skipped", "fallback"}:
            st.caption(f"{event.get('node', 'component')}: {event.get('reason') or event['status']}")

    st.subheader("Agent Trace")
    trace = state.get("trace", [])
    st.write(_trace_path(state) if trace else "No execution trace is available.")
    with st.expander("View Agent Trace"):
        st.json(trace)


def _verification_label(state: AgentState, node: str, field: str) -> str:
    """Keep disabled, placeholder, and absent checks distinct from passes."""
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
    if status not in {"pass", "success"}:
        return "not verified"
    value = state.get(field)
    return "passed" if value is True else "failed" if value is False else "not run"


def _optimizer_label(state: AgentState) -> str:
    """Only report preservation when explicit equality evidence is recorded."""
    events = [event for event in state.get("trace", []) if event.get("node") == "optimizer"]
    if not events:
        return "not run"
    status = events[-1].get("status")
    if status == "skipped":
        return "disabled"
    if status == "placeholder":
        return "starter checks only"
    if status in {"fail", "error"}:
        return "failed"
    if status not in {"pass", "success"}:
        return "not verified"
    final_sql = state.get("optimized_sql") or state.get("sql")
    if state.get("original_sql") and final_sql == state["original_sql"]:
        return "SQL unchanged"
    # Extra JSON-safe metrics/event metadata lets future optimizers supply this
    # evidence without changing the public AgentState or the UI entry point.
    evidence = state.get("metrics", {}).get("optimizer_result_equal")
    if evidence is None:
        evidence = events[-1].get("results_equal")
    if evidence is True:
        return "passed"
    if evidence is False:
        return "result preservation failed"
    return "result preservation not recorded"


def _trace_path(state: AgentState) -> str:
    labels = {
        "schema_retriever": "Schema", "sql_generator": "Generate",
        "safety_verifier": "Safety", "syntax_verifier": "Syntax",
        "semantic_verifier": "Semantic verify", "optimizer": "Optimize",
        "executor": "Execute", "result_verifier": "Result verify",
        "response_generator": "Respond", "repair": "Repair",
    }
    stages = []
    for event in state.get("trace", []):
        stage = labels.get(event.get("node"), event.get("node", "Unknown"))
        if event.get("status") == "skipped":
            stage += " (disabled)"
        stages.append(stage)
    return " → ".join(stages)


if __name__ == "__main__":
    main()
