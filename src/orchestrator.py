"""Replaceable Python routing skeleton for QueryMind's Milestone 2 contracts."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, TypeVar

from src.agents import generate_response, generate_sql
from src.config import Settings, load_settings, resolve_path
from src.db import execute_sql
from src.llm import MockProvider, SQLProvider, get_provider, model_call_count
from src.optimizer import optimize_sql
from src.schema import retrieve_schema, retrieve_schema_with_metadata
from src.state import AgentState
from src.trace import add_trace
from src.verifiers import check_safety, check_syntax, verify_result, verify_semantics

T = TypeVar("T")


@dataclass(frozen=True)
class Components:
    """Inject nodes for isolated tests or replacement without changing AgentState.

    Callables preserve the documented public signatures, including optional
    database/provider keywords on nodes that use those dependencies.
    """

    retrieve_schema: Callable[..., str] = retrieve_schema
    generate_sql: Callable[..., str] = generate_sql
    check_safety: Callable[..., dict[str, Any]] = check_safety
    check_syntax: Callable[..., dict[str, Any]] = check_syntax
    verify_semantics: Callable[..., dict[str, Any]] = verify_semantics
    optimize_sql: Callable[..., dict[str, Any]] = optimize_sql
    execute_sql: Callable[..., dict[str, Any]] = execute_sql
    verify_result: Callable[..., dict[str, Any]] = verify_result
    generate_response: Callable[[AgentState], str] = generate_response


def run_querymind(
    question: str,
    schema_mode: str | None = None,
    enable_syntax: bool = True,
    enable_semantic: bool = True,
    enable_optimizer: bool = True,
    enable_result_verifier: bool = True,
    *,
    db_path: str | Path | None = None,
    provider: SQLProvider | None = None,
    settings: Settings | None = None,
    components: Components | None = None,
) -> AgentState:
    """Run the integrated pipeline, returning JSON-safe state even on node failure.

    Disabling syntax analysis never disables the read-only execution guard.
    The configured provider controls model access; mock mode stays offline.
    """
    started = perf_counter()
    nodes = components or Components()
    state: AgentState = {
        "question": question, "schema_mode": schema_mode or "", "schema_context": "",
        "sql": "", "sql_history": [], "syntax_ok": False, "syntax_error": "",
        "safety_ok": False, "semantic_ok": False, "semantic_reason": "Not checked.",
        "answerable": True, "missing_fields": [], "assumptions": [],
        "original_sql": "", "optimized_sql": "", "optimization_applied": False,
        "original_plan": [], "optimized_plan": [], "rows": [], "columns": [],
        "result_ok": False, "result_warnings": [], "final_answer": "",
        "repair_count": 0, "optimizer_count": 0, "trace": [],
        "metrics": {"llm_calls": 0, "generation_calls": 0},
        "status": "success", "error": "",
    }

    sql_provider = None

    def call_node(name: str, callback: Callable[[], T], *, iteration: int | None = None) -> T:
        node_start = perf_counter()
        before = model_call_count(sql_provider) if sql_provider is not None else 0
        try:
            result = callback()
        except Exception as exc:
            add_trace(state, name, "error", (perf_counter() - node_start) * 1000, str(exc), iteration=iteration)
            raise
        finally:
            after = model_call_count(sql_provider) if sql_provider is not None else 0
            if before is None or after is None:
                state["metrics"]["llm_calls"] = None
            elif state["metrics"]["llm_calls"] is not None:
                state["metrics"]["llm_calls"] += max(0, after - before)
        add_trace(state, name, "pass", (perf_counter() - node_start) * 1000, iteration=iteration)
        return result

    def describe(status: str, reason: str) -> None:
        state["trace"][-1].update(status=status, reason=reason)

    def skipped(name: str, reason: str = "Disabled for ablation.", *, iteration: int | None = None) -> None:
        add_trace(state, name, "skipped", 0.0, reason, iteration=iteration)

    def refuse(reason: str) -> None:
        state.update(status="refused", answerable=False, semantic_reason=reason)

    try:
        if not question.strip():
            refuse("Enter a natural-language question.")
            return _finish(state, nodes, started, provider=sql_provider)
        config = settings or load_settings()
        mode = schema_mode or config.schema.default_mode
        if mode not in {"flat", "neo4j"}:
            raise ValueError("schema_mode must be 'flat' or 'neo4j'")
        if not 0 <= config.orchestrator.max_repairs <= 3 or not 0 <= config.orchestrator.max_optimizer_rounds <= 2:
            raise ValueError("Repair and optimizer budgets must be within 0..3 and 0..2")
        database_path = resolve_path(db_path) if db_path is not None else config.database.path
        sql_provider = provider or get_provider(config.model.provider)
        state["schema_mode"] = mode
        def retrieve() -> str:
            if nodes.retrieve_schema is not retrieve_schema:
                return nodes.retrieve_schema(question, mode=mode, db_path=database_path, top_k=config.schema.top_k)
            retrieved = retrieve_schema_with_metadata(question, mode=mode, db_path=database_path, top_k=config.schema.top_k)
            state["metrics"].update(
                retrieval=retrieved.metrics,
                retrieved_tables=retrieved.tables,
                retrieved_join_paths=[
                    " = ".join(sorted((f"{edge['from_table']}.{edge['from_column']}",
                                       f"{edge['to_table']}.{edge['to_column']}")))
                    for edge in retrieved.relationships
                ],
            )
            return retrieved.context

        state["schema_context"] = call_node("schema_retriever", retrieve)
        if "Neo4j retrieval is a starter placeholder" in state["schema_context"]:
            describe("fallback", state["metrics"].get("retrieval", {}).get("fallback_reason")
                     or "Neo4j unavailable; using flat SQLite schema.")
        feedback = ""
        while True:
            attempt = state["repair_count"] + 1
            state["metrics"]["generation_calls"] += 1
            try:
                state["sql"] = call_node("sql_generator", lambda: nodes.generate_sql(
                    question, state["schema_context"], provider=sql_provider, feedback=feedback or None
                ), iteration=attempt).strip()
            except ValueError as exc:
                refuse(str(exc))
                return _finish(state, nodes, started, provider=sql_provider)
            state["sql_history"].append(state["sql"])
            if state["sql"].upper().startswith("NOT_ANSWERABLE:"):
                state["missing_fields"] = [field.strip() for field in state["sql"].split(":", 1)[1].split(",") if field.strip()]
                refuse("Required data is missing: " + ", ".join(state["missing_fields"]))
                return _finish(state, nodes, started, provider=sql_provider)

            # 1. Safety check (mandatory lexical / policy guard)
            safety = call_node("safety_verifier", lambda: nodes.check_safety(state["sql"]), iteration=attempt)
            state["safety_ok"] = bool(safety["ok"])
            describe("pass" if safety["ok"] else "fail", safety.get("error") or "Read-only guard passed.")
            failure = "" if safety["ok"] else (safety.get("error") or "Read-only safety verification failed.")

            # 2. Syntax check (SQLite EXPLAIN on protected connection)
            if safety["ok"] and enable_syntax:
                syntax = call_node("syntax_verifier", lambda: nodes.check_syntax(state["sql"], db_path=database_path), iteration=attempt)
                state["syntax_ok"] = bool(syntax["ok"])
                failure = "" if syntax["ok"] else (syntax.get("error") or "SQLite syntax verification failed.")
                describe("pass" if syntax["ok"] else "fail", failure or "SQLite compilation passed.")
            elif not enable_syntax:
                skipped("syntax_verifier", iteration=attempt)
            state["syntax_error"] = failure

            # 3. Semantic check (if safety and syntax pass)
            if safety["ok"] and not failure:
                if enable_semantic:
                    semantic = call_node("semantic_verifier", lambda: nodes.verify_semantics(
                        question, state["sql"], state["schema_context"],
                        **({"provider": sql_provider, "use_llm": not getattr(sql_provider, "is_mock", False)
                            and not isinstance(sql_provider, MockProvider)}
                           if nodes.verify_semantics is verify_semantics else {})
                    ), iteration=attempt)
                    placeholder = semantic.get("status") == "placeholder"
                    state.update(
                        semantic_ok=bool(semantic["matches_question"] and semantic["answerable"] and not placeholder),
                        semantic_reason=semantic["reason"],
                        answerable=bool(semantic["answerable"]),
                        missing_fields=list(semantic["missing_fields"]),
                        assumptions=list(semantic["assumptions"]),
                    )
                    describe("placeholder" if placeholder else ("pass" if state["semantic_ok"] else "fail"), semantic["reason"])

                    # If missing required data: refuse immediately without burning repairs
                    if not semantic["answerable"]:
                        refuse(semantic["reason"])
                        return _finish(state, nodes, started, provider=sql_provider)

                    # If semantic mismatch: trigger repair
                    if not semantic["matches_question"]:
                        failure = semantic["reason"]
                else:
                    state["semantic_reason"] = "Semantic verification disabled for ablation."
                    skipped("semantic_verifier", iteration=attempt)

            # If all enabled checks passed: query is verified, proceed to optimization/execution
            if safety["ok"] and not failure:
                break

            # Handle verification failure (safety, syntax, or semantic mismatch)
            if state["repair_count"] >= config.orchestrator.max_repairs:
                refuse("SQL verification failed after the configured repair limit: " + failure)
                return _finish(state, nodes, started, provider=sql_provider)

            state["repair_count"] += 1
            feedback = f"Previous SQL:\n{state['sql']}\n\nVerification failure:\n{failure}"
            add_trace(
                state, "repair", "retry", 0.0,
                f"Repair attempt {state['repair_count']}: {failure}",
                iteration=state["repair_count"] + 1,
            )

        state["original_sql"] = state["sql"]
        if enable_optimizer and config.orchestrator.max_optimizer_rounds:
            for _ in range(config.orchestrator.max_optimizer_rounds):
                optimized = call_node("optimizer", lambda: nodes.optimize_sql(
                    state["sql"], question, state["schema_context"], db_path=database_path,
                    **({"provider": sql_provider} if nodes.optimize_sql is optimize_sql else {})
                ))
                if optimized["changed"]:
                    state["metrics"]["optimizer_result_equal"] = optimized.get("equality_ok")
                state["optimizer_count"] += 1
                if state["optimizer_count"] == 1:
                    state["original_plan"] = optimized["plan_before"]
                state["optimized_plan"] = optimized["plan_after"]
                describe("pass", optimized["reason"])
                if not optimized["changed"]:
                    break
                safety = call_node("safety_verifier", lambda: nodes.check_safety(optimized["sql"]))
                state["safety_ok"] = bool(safety["ok"])
                describe("pass" if safety["ok"] else "fail", safety.get("error") or "Optimizer SQL read-only check.")
                if not safety["ok"]:
                    raise ValueError("Optimizer returned unsafe SQL: " + str(safety.get("error")))
                state["sql"] = optimized["sql"]
                state["sql_history"].append(state["sql"])
                state["optimization_applied"] = True
        else:
            skipped("optimizer", "Disabled for ablation or optimizer budget is zero.")
        state["optimized_sql"] = state["sql"]

        execution = call_node("executor", lambda: nodes.execute_sql(state["sql"], db_path=database_path))
        state.update(rows=execution["rows"], columns=execution["columns"])
        state["metrics"]["execution_time_ms"] = execution["execution_time_ms"]
        if enable_result_verifier:
            result = call_node("result_verifier", lambda: nodes.verify_result(
                question, state["sql"], state["rows"], state["columns"],
                **({"schema_context": state["schema_context"], "provider": sql_provider,
                    "use_llm": not getattr(sql_provider, "is_mock", False) and not isinstance(sql_provider, MockProvider)}
                   if nodes.verify_result is verify_result else {})
            ))
            placeholder = result.get("status") == "placeholder"
            state["result_ok"] = bool(result["ok"] and not placeholder)
            state["result_warnings"] = list(result["warnings"])
            state["metrics"]["result_statistics"] = result["statistics"]
            describe("placeholder" if placeholder else ("pass" if result["ok"] else "fail"), "; ".join(result["warnings"]))
            if not result["ok"]:
                state.update(status="error", error="Result structure failed verification.")
        else:
            state["result_warnings"] = ["Result verification disabled for ablation."]
            skipped("result_verifier")
    except Exception as exc:
        state.update(status="error", error=str(exc))
    return _finish(state, nodes, started, provider=sql_provider)


def _finish(state: AgentState, nodes: Components, started: float, *, provider: SQLProvider | None = None) -> AgentState:
    """Always produce a response and total timing, including refusal/error paths."""
    response_start = perf_counter()
    try:
        before = model_call_count(provider) if provider is not None else 0
        try:
            state["final_answer"] = nodes.generate_response(
                state, **({"provider": provider} if nodes.generate_response is generate_response else {})
            )
        finally:
            after = model_call_count(provider) if provider is not None else 0
            if before is None or after is None:
                state["metrics"]["llm_calls"] = None
            elif state["metrics"]["llm_calls"] is not None:
                state["metrics"]["llm_calls"] += max(0, after - before)
        add_trace(state, "response_generator", "pass", (perf_counter() - response_start) * 1000)
    except Exception as exc:
        state.update(status="error", error=str(exc), final_answer="QueryMind could not format the response.")
        add_trace(state, "response_generator", "error", (perf_counter() - response_start) * 1000, str(exc))
    state["metrics"]["total_latency_ms"] = round((perf_counter() - started) * 1000, 3)
    return state
