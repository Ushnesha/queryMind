"""Integration contracts for independently replaceable nodes and routing."""

from dataclasses import replace
import json

from src.config import OrchestratorSettings, Settings
from src.db import execute_sql
from src.orchestrator import Components, run_querymind
from src.state import AgentState
from src.trace import write_jsonl

QUESTION = "Who are the top 3 customers by total spending?"


def test_state_supports_starter_fields() -> None:
    state: AgentState = {"question": QUESTION, "sql_history": [], "trace": [], "metrics": {}}
    assert json.loads(json.dumps(state))["question"] == QUESTION


def test_orchestrator_offline_smoke(db_path) -> None:
    state = run_querymind(QUESTION, schema_mode="flat", db_path=db_path)
    assert state["status"] == "success"
    assert state["rows"] == [["Alice Chen", 300.0], ["Bob Smith", 175.0], ["Carol Davis", 75.0]]
    assert state["syntax_ok"] and state["safety_ok"]
    assert not state["semantic_ok"] and not state["result_ok"]
    assert state["optimizer_count"] == 1 and not state["optimization_applied"]
    assert json.loads(json.dumps(state))["final_answer"]


def test_nodes_can_be_replaced_without_database_or_services(tmp_path) -> None:
    nodes = replace(
        Components(),
        retrieve_schema=lambda *args, **kwargs: "TABLE demo (value INTEGER)",
        generate_sql=lambda *args, **kwargs: "SELECT 42 AS value",
        check_syntax=lambda *args, **kwargs: {"ok": True, "error": None},
        optimize_sql=lambda sql, *args, **kwargs: {
            "changed": False, "sql": sql, "reason": "stub", "plan_before": [], "plan_after": []
        },
        execute_sql=lambda *args, **kwargs: {"rows": [[42]], "columns": ["value"], "execution_time_ms": 0.0},
    )
    state = run_querymind(QUESTION, components=nodes, db_path=tmp_path / "missing.db")
    assert state["status"] == "success" and state["rows"] == [[42]]


def test_neo4j_is_explicit_offline_fallback(db_path) -> None:
    state = run_querymind(QUESTION, schema_mode="neo4j", db_path=db_path)
    assert state["status"] == "success"
    assert state["trace"][0]["status"] == "placeholder"


def test_ablation_skips_optional_nodes_but_retains_readonly_safety(db_path) -> None:
    state = run_querymind(QUESTION, db_path=db_path, enable_syntax=False, enable_semantic=False,
                          enable_optimizer=False, enable_result_verifier=False)
    skipped = {event["node"] for event in state["trace"] if event["status"] == "skipped"}
    assert skipped == {"syntax_verifier", "semantic_verifier", "optimizer", "result_verifier"}
    assert state["status"] == "success" and state["safety_ok"]


def test_repairs_stop_at_three_and_do_not_execute(db_path) -> None:
    nodes = replace(Components(), generate_sql=lambda *args, **kwargs: "SELECT absent FROM customers")
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "refused" and state["repair_count"] == 3
    assert len(state["sql_history"]) == 4
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_repair_feedback_allows_replacement_generator_to_recover(db_path) -> None:
    feedback_values = []

    def generator(*args, feedback=None, **kwargs) -> str:
        feedback_values.append(feedback)
        return "SELECT 1 AS value" if feedback else "SELECT absent FROM customers"

    state = run_querymind(QUESTION, db_path=db_path, components=replace(Components(), generate_sql=generator))
    assert state["status"] == "success" and state["repair_count"] == 1
    assert feedback_values[0] is None and "absent" in feedback_values[1]


def test_false_syntax_flag_without_error_message_does_not_execute(db_path) -> None:
    nodes = replace(Components(), check_syntax=lambda *args, **kwargs: {"ok": False, "error": None})
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "refused" and state["repair_count"] == 3
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_semantic_refusal_stops_execution(db_path) -> None:
    nodes = replace(Components(), verify_semantics=lambda *args: {
        "matches_question": False, "answerable": False, "missing_fields": ["profit"],
        "assumptions": [], "reason": "Profit is unavailable."
    })
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "refused" and state["missing_fields"] == ["profit"]
    assert "profit" in state["final_answer"]
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_executor_safety_survives_disabled_analysis_and_replaced_verifier(db_path) -> None:
    nodes = replace(Components(), generate_sql=lambda *args, **kwargs: "DELETE FROM customers",
                    check_safety=lambda sql: {"ok": True, "error": None})
    state = run_querymind(QUESTION, db_path=db_path, components=nodes, enable_syntax=False,
                          enable_semantic=False, enable_optimizer=False)
    assert state["status"] == "error"
    assert execute_sql("SELECT COUNT(*) FROM customers", db_path=db_path)["rows"] == [[4]]


def test_optimizer_rounds_are_bounded(db_path) -> None:
    nodes = replace(Components(), optimize_sql=lambda *args, **kwargs: {
        "changed": True, "sql": "SELECT 1 AS value", "reason": "stub candidate", "plan_before": [], "plan_after": []
    })
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "success" and state["optimizer_count"] == 2


def test_unsupported_mock_question_refuses(db_path) -> None:
    state = run_querymind("Show customer profits", db_path=db_path)
    assert state["status"] == "refused" and "offline mock" in state["final_answer"]


def test_missing_database_returns_error_without_creating_file(tmp_path) -> None:
    target = tmp_path / "missing.db"
    state = run_querymind(QUESTION, db_path=target)
    assert state["status"] == "error" and not target.exists()


def test_zero_repair_budget_stops_after_initial_attempt(db_path) -> None:
    settings = replace(Settings(), orchestrator=OrchestratorSettings(max_repairs=0))
    nodes = replace(Components(), generate_sql=lambda *args, **kwargs: "DROP TABLE customers")
    state = run_querymind(QUESTION, db_path=db_path, settings=settings, components=nodes)
    assert state["status"] == "refused" and len(state["sql_history"]) == 1


def test_jsonl_trace_can_round_trip(db_path, tmp_path) -> None:
    state = run_querymind(QUESTION, db_path=db_path)
    path = tmp_path / "runs.jsonl"
    write_jsonl(path, state)
    assert json.loads(path.read_text())["rows"] == state["rows"]


def test_semantic_mismatch_routes_to_repair_and_succeeds(db_path) -> None:
    calls = []

    def fake_generator(*args, feedback=None, **kwargs) -> str:
        calls.append(feedback)
        return "SELECT 2 AS value" if feedback else "SELECT 1 AS value"

    def fake_semantics(q, sql, schema):
        if "1" in sql:
            return {
                "matches_question": False,
                "answerable": True,
                "missing_fields": [],
                "assumptions": [],
                "reason": "Query does not filter by target category.",
            }
        return {
            "matches_question": True,
            "answerable": True,
            "missing_fields": [],
            "assumptions": ["Category filter verified."],
            "reason": "Query semantics match.",
        }

    nodes = replace(Components(), generate_sql=fake_generator, verify_semantics=fake_semantics)
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "success"
    assert state["repair_count"] == 1
    assert state["metrics"]["llm_calls"] == 2
    assert state["sql"] == "SELECT 2 AS value"
    assert state["assumptions"] == ["Category filter verified."]
    assert "category" in calls[1].lower()
    assert any(event["node"] == "executor" for event in state["trace"])


def test_syntax_failure_then_semantic_mismatch_recovers(db_path) -> None:
    attempt = 0

    def fake_generator(*args, **kwargs) -> str:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            return "SELECT nonexistent FROM customers"  # syntax fail
        if attempt == 2:
            return "SELECT 1 AS value"  # syntax pass, semantic fail
        return "SELECT 2 AS value"  # syntax pass, semantic pass

    def fake_semantics(q, sql, schema):
        if "1" in sql:
            return {
                "matches_question": False,
                "answerable": True,
                "missing_fields": [],
                "assumptions": [],
                "reason": "Missing expected grouping.",
            }
        return {
            "matches_question": True,
            "answerable": True,
            "missing_fields": [],
            "assumptions": ["Valid grouping."],
            "reason": "Semantic match.",
        }

    nodes = replace(Components(), generate_sql=fake_generator, verify_semantics=fake_semantics)
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "success"
    assert state["repair_count"] == 2
    assert state["metrics"]["llm_calls"] == 3
    assert state["sql"] == "SELECT 2 AS value"


def test_shared_repair_budget_exhaustion_mixing_syntax_and_semantics(db_path) -> None:
    attempt = 0

    def fake_generator(*args, **kwargs) -> str:
        nonlocal attempt
        attempt += 1
        if attempt % 2 == 1:
            return "SELECT nonexistent FROM customers"  # syntax fail on attempts 1 and 3
        return "SELECT 1 AS value"  # syntax pass, semantic fail on attempts 2 and 4

    def fake_semantics(q, sql, schema):
        return {
            "matches_question": False,
            "answerable": True,
            "missing_fields": [],
            "assumptions": [],
            "reason": "Semantic mismatch.",
        }

    nodes = replace(Components(), generate_sql=fake_generator, verify_semantics=fake_semantics)
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "refused"
    assert state["repair_count"] == 3
    assert state["metrics"]["llm_calls"] == 4
    assert len(state["sql_history"]) == 4
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_semantic_unanswerable_refuses_immediately_without_repair(db_path) -> None:
    gen_count = 0

    def fake_generator(*args, **kwargs) -> str:
        nonlocal gen_count
        gen_count += 1
        return "SELECT 1 AS value"

    def fake_semantics(q, sql, schema):
        return {
            "matches_question": False,
            "answerable": False,
            "missing_fields": ["cost"],
            "assumptions": [],
            "reason": "Profit margin requires cost information not in schema.",
        }

    nodes = replace(Components(), generate_sql=fake_generator, verify_semantics=fake_semantics)
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)
    assert state["status"] == "refused"
    assert state["repair_count"] == 0
    assert state["metrics"]["llm_calls"] == 1
    assert gen_count == 1
    assert state["missing_fields"] == ["cost"]
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_llm_calls_metric_tracking(db_path) -> None:
    # 1. Happy path: exactly 1 LLM call
    state_smoke = run_querymind(QUESTION, schema_mode="flat", db_path=db_path)
    assert state_smoke["metrics"]["llm_calls"] == 1

    # 2. Empty question: 0 LLM calls
    state_empty = run_querymind("", db_path=db_path)
    assert state_empty["metrics"]["llm_calls"] == 0

    # 3. 1 repair: 2 LLM calls
    state_repair = run_querymind(
        QUESTION,
        db_path=db_path,
        components=replace(
            Components(),
            generate_sql=lambda *args, feedback=None, **kwargs: (
                "SELECT 1 AS value" if feedback else "SELECT absent FROM customers"
            ),
        ),
    )
    assert state_repair["metrics"]["llm_calls"] == 2


def test_trace_iteration_enrichment(db_path) -> None:
    attempt = 0

    def fake_generator(*args, **kwargs) -> str:
        nonlocal attempt
        attempt += 1
        return "SELECT 1 AS value" if attempt > 1 else "SELECT absent FROM customers"

    nodes = replace(Components(), generate_sql=fake_generator)
    state = run_querymind(QUESTION, db_path=db_path, components=nodes)

    gen_events = [e for e in state["trace"] if e["node"] == "sql_generator"]
    assert len(gen_events) == 2
    assert gen_events[0]["iteration"] == 1
    assert gen_events[1]["iteration"] == 2

    retry_events = [e for e in state["trace"] if e["status"] == "retry"]
    assert len(retry_events) == 1
    assert retry_events[0]["iteration"] == 2  # retry points to upcoming attempt 2

    # Non-loop nodes should omit iteration
    schema_events = [e for e in state["trace"] if e["node"] == "schema_retriever"]
    assert "iteration" not in schema_events[0]


def test_semantic_disabled_ablation_skips_semantic_repair(db_path) -> None:
    nodes = replace(
        Components(),
        generate_sql=lambda *args, **kwargs: "SELECT 1 AS value",
        verify_semantics=lambda *args: {
            "matches_question": False,
            "answerable": False,
            "missing_fields": ["fake"],
            "assumptions": [],
            "reason": "Would fail if called.",
        },
    )
    state = run_querymind(QUESTION, db_path=db_path, components=nodes, enable_semantic=False)
    assert state["status"] == "success"
    assert any(e["node"] == "semantic_verifier" and e["status"] == "skipped" for e in state["trace"])

