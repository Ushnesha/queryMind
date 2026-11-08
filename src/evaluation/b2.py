"""Reduced preliminary b2 experiment: vote on executed results, never SQL text.

The default is k=3 rather than the final proposal's k=5. Generation attempts are
reported separately from model calls: the offline MockProvider makes zero LLM
calls. Other providers need explicit ``llm_calls`` counters; otherwise their
model-call count stays unknown rather than assuming each generation is one call.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from src.agents import generate_response, generate_sql
from src.db import execute_sql, introspect_schema
from src.llm import MockProvider, SQLProvider, get_provider
from src.score import normalize_result
from src.state import AgentState
from src.trace import add_trace


def _empty_state(question: str) -> AgentState:
    return {
        "question": question, "schema_mode": "flat", "schema_context": "",
        "sql": "", "sql_history": [], "rows": [], "columns": [],
        "status": "success", "answerable": True, "missing_fields": [],
        "assumptions": [], "semantic_reason": "", "error": "",
        "final_answer": "", "trace": [], "metrics": {
            "generation_calls": 0, "llm_calls": 0,
        },
    }


def _finish(state: AgentState, started: float) -> AgentState:
    if state.get("status") == "refused" and state.get("answerable", True):
        state["final_answer"] = "QueryMind cannot reliably answer this question. " + state.get("semantic_reason", "")
    else:
        state["final_answer"] = generate_response(state)
    state["metrics"]["total_latency_ms"] = round((perf_counter() - started) * 1000, 3)
    return state


def _model_counter(provider: SQLProvider) -> int | None:
    if isinstance(provider, MockProvider) or getattr(provider, "is_mock", False):
        return 0
    value = getattr(provider, "llm_calls", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _candidate(
    question: str, schema: str, provider: SQLProvider, db_path: str | Path | None,
) -> AgentState:
    started = perf_counter()
    state = _empty_state(question)
    state["schema_context"] = schema
    state["metrics"]["provider"] = type(provider).__name__
    node_started = perf_counter()
    calls_before = _model_counter(provider)
    state["metrics"].update(generation_calls=1, llm_calls=None)
    try:
        sql = generate_sql(question, schema, provider=provider).strip()
        state["sql"] = sql
        state["sql_history"].append(sql)
        if sql.upper().startswith("NOT_ANSWERABLE:"):
            fields = [field.strip() for field in sql.split(":", 1)[1].split(",") if field.strip()]
            state.update(
                status="refused", answerable=False, missing_fields=fields,
                semantic_reason="The SQL generator reported unavailable information."
                + (" Missing fields: " + ", ".join(fields) if fields else ""),
            )
            add_trace(state, "sql_generator", "refused", (perf_counter() - node_started) * 1000,
                      state["semantic_reason"])
            return _finish(state, started)
        add_trace(state, "sql_generator", "pass", (perf_counter() - node_started) * 1000)
    except ValueError as exc:
        # The current mock raises ValueError for unsupported questions. This is
        # an abstention and does not prove that the database lacks a field.
        state.update(status="refused", semantic_reason=str(exc))
        add_trace(state, "sql_generator", "refused", (perf_counter() - node_started) * 1000, str(exc))
        return _finish(state, started)
    except Exception as exc:
        state.update(status="error", error=str(exc))
        add_trace(state, "sql_generator", "error", (perf_counter() - node_started) * 1000, str(exc))
        return _finish(state, started)
    finally:
        calls_after = _model_counter(provider)
        if calls_before is not None and calls_after is not None:
            state["metrics"]["llm_calls"] = max(0, calls_after - calls_before)

    node_started = perf_counter()
    try:
        # execute_sql always applies the shared read-only guard and SQLite
        # authorizer; these remain active for every baseline and b2 candidate.
        result = execute_sql(sql, db_path=db_path)
        state.update(rows=result["rows"], columns=result["columns"])
        state["metrics"]["execution_time_ms"] = result["execution_time_ms"]
        add_trace(state, "executor", "pass", (perf_counter() - node_started) * 1000)
    except Exception as exc:
        state.update(status="error", error=str(exc))
        add_trace(state, "executor", "error", (perf_counter() - node_started) * 1000, str(exc))
    return _finish(state, started)


def run_single_generation(
    question: str, *, db_path: str | Path | None = None,
    provider: SQLProvider | None = None,
) -> AgentState:
    """Run the b1 generation/execution components once, with no agent checks.

    This uses the baseline's provider/schema/executor boundaries and adds a
    serializable outcome plus accounting. It never invokes agent verification,
    repair, optimization, or an LLM judge.
    """
    started = perf_counter()
    try:
        schema = introspect_schema(db_path)
        sql_provider = provider or get_provider()
    except Exception as exc:
        state = _empty_state(question)
        state.update(status="error", error=str(exc))
        add_trace(state, "schema_retriever", "error", (perf_counter() - started) * 1000, str(exc))
        return _finish(state, started)
    retrieval_ms = (perf_counter() - started) * 1000
    state = _candidate(question, schema, sql_provider, db_path)
    state["trace"].insert(0, {
        "node": "schema_retriever", "status": "pass",
        "latency_ms": round(retrieval_ms, 3), "reason": "Baseline flat SQLite schema.",
    })
    return _finish(state, started)


def run_self_consistency(
    question: str, *, samples: int = 3, db_path: str | Path | None = None,
    provider: SQLProvider | None = None,
) -> dict[str, Any]:
    """Generate k independent SQL candidates and select a strict result majority.

    Agreement uses the shared scorer's exact column labels, JSON cell types,
    and unordered row multisets (including duplicates). A majority must exceed
    half of *all requested* samples; failed candidates never vote. The first
    candidate in the winning group is a deterministic representative. Ties and
    pluralities abstain. Refusal consensus is reported separately from a SQL
    result majority and never counted as an executable result.
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("samples must be a positive integer")
    started = perf_counter()
    label = f"b2-small preliminary experiment (k={samples})"
    report: dict[str, Any] = {
        "implemented": True, "question": question, "samples": samples,
        "label": label, "scope": label + (
            "; reduced from the final proposed k=5" if samples < 5 else "; final proposal uses k=5"
        ),
        "candidates": [], "selected_index": None, "majority_count": 0,
        "required_votes": samples // 2 + 1,
        "agreement_policy": "strict majority of all samples; shared unordered result multiset scorer",
    }
    try:
        schema = introspect_schema(db_path)
        sql_provider = provider or get_provider()
    except Exception as exc:
        state = _empty_state(question)
        state.update(status="error", error=str(exc))
        add_trace(state, "schema_retriever", "error", (perf_counter() - started) * 1000, str(exc))
        report["state"] = _finish(state, started)
        return report

    retrieval_ms = (perf_counter() - started) * 1000
    candidates = [_candidate(question, schema, sql_provider, db_path) for _ in range(samples)]
    report["candidates"] = candidates
    groups: dict[str, list[int]] = defaultdict(list)
    refusal_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        if candidate["status"] == "success":
            key = json.dumps(normalize_result(candidate["rows"], candidate["columns"]), sort_keys=True)
            groups[key].append(index)
        elif candidate["status"] == "refused" and candidate.get("answerable") is False:
            refusal_groups[tuple(sorted(candidate.get("missing_fields", [])))].append(index)
    winning_group = max(groups.values(), key=len, default=[])
    report["majority_count"] = len(winning_group)
    state = _empty_state(question)
    state["schema_context"] = schema
    state["metrics"]["provider"] = type(sql_provider).__name__
    state["sql_history"] = [candidate["sql"] for candidate in candidates if candidate.get("sql")]
    if len(winning_group) >= report["required_votes"]:
        selected_index = winning_group[0]
        report["selected_index"] = selected_index
        selected = candidates[selected_index]
        state.update(sql=selected["sql"], rows=selected["rows"], columns=selected["columns"])
        selection_status = "pass"
        reason = f"Selected candidate {selected_index + 1}: {len(winning_group)}/{samples} results agree."
    else:
        state["status"] = "refused"
        reason = f"No strict result majority: largest group {len(winning_group)}/{samples}; {report['required_votes']} required."
        state["semantic_reason"] = reason
        refusal_group = max(refusal_groups.values(), key=len, default=[])
        if len(refusal_group) >= report["required_votes"]:
            refusal = candidates[refusal_group[0]]
            state.update(answerable=False, missing_fields=refusal.get("missing_fields", []),
                         semantic_reason=refusal.get("semantic_reason", reason))
            report["refusal_consensus_count"] = len(refusal_group)
        state["final_answer"] = "QueryMind cannot reliably answer this question. " + reason
        selection_status = "refused"
    add_trace(state, "schema_retriever", "pass", retrieval_ms, "Shared flat SQLite schema for all candidates.")
    for index, candidate in enumerate(candidates):
        state["trace"].append({
            "node": "b2_candidate", "status": candidate["status"], "iteration": index + 1,
            "latency_ms": candidate["metrics"]["total_latency_ms"],
            "reason": candidate.get("error") or candidate.get("semantic_reason") or "Read-only SQL executed.",
        })
    add_trace(state, "b2_selection", selection_status, 0.0, reason)
    model_counts = [candidate["metrics"]["llm_calls"] for candidate in candidates]
    state["metrics"].update(
        generation_calls=sum(candidate["metrics"]["generation_calls"] for candidate in candidates),
        llm_calls=sum(model_counts) if all(value is not None for value in model_counts) else None,
        successful_candidates=sum(candidate["status"] == "success" for candidate in candidates),
    )
    timings = [candidate["metrics"]["execution_time_ms"] for candidate in candidates
               if "execution_time_ms" in candidate["metrics"]]
    if timings:
        state["metrics"]["execution_time_ms"] = sum(timings)
    if state["status"] == "success" or state.get("answerable") is False:
        state["final_answer"] = generate_response(state)
    state["metrics"]["total_latency_ms"] = round((perf_counter() - started) * 1000, 3)
    report["state"] = state
    return report
