"""Map QueryMind states onto the stakeholder baseline's trace format.

The stakeholder scorer (`external/agentic-sql-analyst/src/score.py`) decides
correctness from these trace fields only: ``refused``, ``missing_field``,
``assumptions``, ``exec_ok`` and ``sql`` (re-executed against the reference).
Writing QueryMind runs in that format lets b0, b1 and QueryMind be judged by
one unchanged scorer. Extra QueryMind fields are kept for behaviour metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

# Pipeline notices that the semantic verifier appends to `assumptions`. They
# describe infrastructure, not an interpretation of the user's question, so
# they must not earn ambiguity-flagging credit.
INFRASTRUCTURE_NOTE_PREFIXES = (
    "Schema retrieval note:",
    "LLM semantic judge unavailable",
)
PROVIDER_ERROR_PREFIXES = (
    "Provider HTTP error",
    "Provider network error",
    "Provider connection error",
    "Provider returned invalid response",
)


def interpretation_assumptions(assumptions: list[str] | None) -> list[str]:
    """Return assumptions that state an interpretation of the question."""
    return [
        text for text in (assumptions or [])
        if text and not text.startswith(INFRASTRUCTURE_NOTE_PREFIXES)
    ]


def is_provider_error(text: str | None) -> bool:
    return bool(text) and any(prefix in text for prefix in PROVIDER_ERROR_PREFIXES)


def to_stakeholder_record(
    question_id: str,
    question: str,
    state: Mapping[str, Any],
    *,
    model: str,
    provider_name: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    calls_without_usage: int | None = None,
    run_tag: str | None = None,
    arm: str = "querymind",
) -> dict[str, Any]:
    """Build one stakeholder-format trace record from a final AgentState."""
    status = state.get("status")
    metrics = state.get("metrics") or {}
    reason = state.get("semantic_reason") or ""
    error = state.get("error") or ""
    sql_history = list(state.get("sql_history") or [])
    first_sql = sql_history[0] if sql_history else ""

    provider_failure = status == "refused" and is_provider_error(reason) or is_provider_error(error)
    refused = status == "refused" and not provider_failure
    executed = status == "success" and any(
        step.get("node") == "executor" and step.get("status") == "pass" for step in state.get("trace") or []
    )
    if provider_failure:
        error_type, error_text = "ProviderError", (reason if status == "refused" else error)
    elif status == "error":
        error_type = "ResultVerificationFailed" if "Result structure failed" in error else "PipelineError"
        error_text = error
    elif refused and reason.startswith("SQL verification failed after the configured repair limit"):
        error_type, error_text = "RepairLimitReached", reason
    else:
        error_type, error_text = None, None

    interpretations = interpretation_assumptions(state.get("assumptions"))
    retrieval = metrics.get("retrieval") or {}
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_tag": run_tag,
        "question_id": question_id,
        "question": question,
        "arm": arm,
        "schema_mode": state.get("schema_mode"),
        "prompt_version": "querymind-m3",
        "provider": provider_name,
        "model": model,
        "temperature": 0.0,
        "sql": state.get("sql") or "",
        "refused": refused,
        "missing_field": ", ".join(state.get("missing_fields") or []) or None,
        "assumptions": "; ".join(interpretations) or None,
        "exec_ok": executed,
        "rows": len(state.get("rows") or []) if executed else None,
        "truncated": False,
        "error_type": error_type,
        "error": (error_text or "")[:500] or None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": metrics.get("total_latency_ms"),
        # QueryMind-only behaviour fields (ignored by the stakeholder scorer).
        "qm_status": status,
        "qm_reason": reason[:500],
        "qm_assumptions_raw": list(state.get("assumptions") or []),
        "qm_llm_calls": metrics.get("llm_calls"),
        "qm_generation_calls": metrics.get("generation_calls"),
        "qm_calls_without_usage": calls_without_usage,
        "qm_repair_count": state.get("repair_count", 0),
        "qm_first_sql": first_sql,
        "qm_first_attempt_ok": not any(
            step.get("node") in {"safety_verifier", "syntax_verifier", "semantic_verifier"}
            and step.get("status") == "fail" and step.get("iteration") == 1
            for step in state.get("trace") or []
        ),
        "qm_optimizer_rounds": state.get("optimizer_count", 0),
        "qm_optimization_applied": bool(state.get("optimization_applied")),
        "qm_original_sql": state.get("original_sql") or "",
        "qm_optimizer_result_equal": metrics.get("optimizer_result_equal"),
        "qm_result_warnings": list(state.get("result_warnings") or []),
        "qm_schema_backend": retrieval.get("backend"),
        "qm_schema_fallback": retrieval.get("backend") == "flat_fallback",
        "qm_schema_note": retrieval.get("fallback_reason") or None,
        "qm_retrieved_tables": metrics.get("retrieved_tables"),
        "qm_final_answer": (state.get("final_answer") or "")[:1000],
    }
