"""R1 flat-schema retry in the orchestrator (spec: docs/R1_SCHEMA_RETRY.md section 7)."""

from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from src.config import OrchestratorSettings, Settings
from src.evaluation.ablation import ablation_variants, experiment_variants
from src.evaluation.stakeholder import to_stakeholder_record
from src.orchestrator import Components, run_querymind

QUESTION = "What is the total revenue by region?"
NEO4J_CTX = "TABLE customers (customer_id INTEGER, region TEXT)"
FLAT_CTX = "TABLE customers (customer_id INTEGER, region TEXT)\nTABLE orders (customer_id INTEGER, total_amount REAL)"
FLAT_SQL = ("SELECT c.region, SUM(o.total_amount) FROM customers c "
            "JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.region")
NEO4J_SQL = "SELECT region, COUNT(*) FROM customers GROUP BY region"
PLACEHOLDER_CTX = "Neo4j retrieval is a starter placeholder; using flat SQLite schema.\n" + FLAT_CTX
ROWS = [["East", 10.0], ["West", 20.0]]


def _semantic(ok=True, answerable=True, reason="ok", missing=()):
    return {"matches_question": ok, "answerable": answerable, "reason": reason,
            "missing_fields": list(missing), "assumptions": [], "status": "checked"}


def _nodes(trigger: str | None, *, flat_refuses: bool = False, neo4j_ctx: str = NEO4J_CTX, **overrides):
    """Neo4j context lacks `orders`; the flat context has it. Behaviour keys on the context."""
    calls = {"retrieve_modes": [], "executed": 0}

    def retrieve(question, *, mode, **kwargs):
        calls["retrieve_modes"].append(mode)
        return neo4j_ctx if mode == "neo4j" else FLAT_CTX

    def generate(question, context, **kwargs):
        if context == FLAT_CTX:
            return "NOT_ANSWERABLE: revenue" if flat_refuses == "not_answerable" else FLAT_SQL
        if trigger == "not_answerable":
            return "NOT_ANSWERABLE: revenue, total_amount"
        return NEO4J_SQL

    def semantics(question, sql, context, **kwargs):
        if context == FLAT_CTX:
            if flat_refuses == "semantic_unanswerable":
                return _semantic(answerable=False, reason="Flat: no revenue column.", missing=["flat_field"])
            return _semantic(reason="Flat SQL answers the question.")
        if trigger == "semantic_unanswerable":
            return _semantic(answerable=False, reason="Revenue is not in the schema.", missing=["revenue"])
        if trigger == "repairs_exhausted":
            return _semantic(ok=False, reason="Counts rows, not revenue.")
        return _semantic(reason="Neo4j SQL answers the question.")

    def execute(sql, **kwargs):
        calls["executed"] += 1
        return {"rows": ROWS, "columns": ["region", "revenue"], "execution_time_ms": 0.1}

    nodes = replace(Components(), **{
        "retrieve_schema": retrieve, "generate_sql": generate, "verify_semantics": semantics,
        "check_syntax": lambda *a, **k: {"ok": True, "error": None},
        "optimize_sql": lambda sql, *a, **k: {"changed": False, "sql": sql, "reason": "stub",
                                              "plan_before": [], "plan_after": []},
        "execute_sql": execute,
        "verify_result": lambda *a, **k: {"ok": True, "warnings": [], "statistics": {}},
        **overrides,
    })
    return nodes, calls


def _run(nodes, *, schema_mode="neo4j", repairs=3, retry_repairs=1, **kwargs):
    settings = Settings(orchestrator=OrchestratorSettings(repairs, 2, retry_repairs))
    return run_querymind(QUESTION, schema_mode=schema_mode, settings=settings, components=nodes,
                         db_path="unused.db", **kwargs)


def _events(state, node):
    return [event for event in state["trace"] if event["node"] == node]


@pytest.mark.parametrize("trigger", ["not_answerable", "semantic_unanswerable", "repairs_exhausted"])
def test_neo4j_refusal_is_answered_by_flat_retry(trigger) -> None:
    nodes, calls = _nodes(trigger)
    state = _run(nodes)
    assert state["status"] == "success" and state["rows"] == ROWS
    assert state["schema_context"] == FLAT_CTX and state["sql"] == FLAT_SQL
    assert state["metrics"]["schema_retry"] == {"triggered": True, "trigger": trigger, "outcome": "answered"}
    assert calls["retrieve_modes"] == ["neo4j", "flat"]
    neo4j_generations = 4 if trigger == "repairs_exhausted" else 1
    assert state["metrics"]["generation_calls"] == neo4j_generations + 1
    generations = _events(state, "sql_generator")
    assert [event["iteration"] for event in generations] == list(range(1, neo4j_generations + 2))
    assert generations[-1]["iteration"] > 1
    assert state["repair_count"] == (3 if trigger == "repairs_exhausted" else 0)


@pytest.mark.parametrize("flat_refuses", ["not_answerable", "semantic_unanswerable"])
def test_flat_retry_also_refusing_keeps_neo4j_reason_and_fields(flat_refuses) -> None:
    nodes, calls = _nodes("semantic_unanswerable", flat_refuses=flat_refuses)
    state = _run(nodes)
    assert state["status"] == "refused" and not state["answerable"]
    assert state["semantic_reason"].startswith("Revenue is not in the schema.")
    assert "Flat-schema retry also refused" in state["semantic_reason"]
    assert state["missing_fields"] == ["revenue"]  # Neo4j attempt's list wins
    assert state["schema_context"] == NEO4J_CTX
    assert state["metrics"]["schema_retry"]["outcome"] == "refused"
    assert calls["executed"] == 0


def test_repairs_exhausted_without_neo4j_fields_falls_back_to_flat_fields() -> None:
    nodes, _ = _nodes("repairs_exhausted", flat_refuses="semantic_unanswerable")
    state = _run(nodes)
    assert state["semantic_reason"].startswith("SQL verification failed after the configured repair limit")
    assert state["missing_fields"] == ["flat_field"]
    record = to_stakeholder_record("E3", QUESTION, state, model="m", provider_name="p",
                                   prompt_tokens=None, completion_tokens=None)
    assert record["error_type"] == "RepairLimitReached"


def test_unanswerable_question_stays_refused_and_never_executes() -> None:
    nodes, calls = _nodes("not_answerable", flat_refuses="not_answerable")
    state = _run(nodes)
    assert state["status"] == "refused" and calls["executed"] == 0
    assert not _events(state, "executor")
    assert state["missing_fields"] == ["revenue", "total_amount"]


def test_never_a_second_retry() -> None:
    nodes, _ = _nodes("not_answerable", flat_refuses="not_answerable")
    state = _run(nodes)
    assert len(_events(state, "schema_retry")) == 1
    assert len(_events(state, "schema_retriever")) == 2


def test_flat_retry_has_its_own_repair_budget() -> None:
    nodes, _ = _nodes("repairs_exhausted")
    flat_mismatch = replace(nodes, verify_semantics=lambda q, sql, ctx, **k: _semantic(ok=False, reason="mismatch"))
    state = _run(flat_mismatch, repairs=2, retry_repairs=1)
    # 3 Neo4j generations (2 repairs) + 2 flat generations (1 repair); total repairs stays cumulative.
    assert state["metrics"]["generation_calls"] == 5 and state["repair_count"] == 3
    assert state["status"] == "refused"


@pytest.mark.parametrize("schema_mode,context", [("flat", FLAT_CTX), ("neo4j", PLACEHOLDER_CTX)])
def test_no_retry_in_flat_mode_or_neo4j_fallback(schema_mode, context) -> None:
    nodes, calls = _nodes("not_answerable", neo4j_ctx=context)
    nodes = replace(nodes, generate_sql=lambda *a, **k: "NOT_ANSWERABLE: revenue")
    state = _run(nodes, schema_mode=schema_mode)
    assert state["status"] == "refused"
    assert state["metrics"]["schema_retry"] == {"triggered": False, "trigger": None, "outcome": None}
    assert not _events(state, "schema_retry") and len(calls["retrieve_modes"]) == 1


def test_no_retry_when_neo4j_already_returned_full_schema(monkeypatch) -> None:
    retrieved = SimpleNamespace(context=NEO4J_CTX, tables=["customers"], relationships=[],
                                metrics={"backend": "neo4j",
                                         "fallback_reason": "No identifier matches; returned the full schema."})
    monkeypatch.setattr("src.orchestrator.retrieve_schema_with_metadata", lambda *a, **k: retrieved)
    nodes, _ = _nodes("not_answerable")
    nodes = replace(nodes, retrieve_schema=Components().retrieve_schema)
    state = _run(nodes)
    assert state["status"] == "refused" and state["metrics"]["schema_retry"]["triggered"] is False


@pytest.mark.parametrize("exc", [RuntimeError("generator crashed"), ValueError("Provider HTTP error 500: down")])
def test_errors_and_provider_failures_never_retry(exc) -> None:
    def broken(*args, **kwargs):
        raise exc

    nodes, calls = _nodes(None, generate_sql=broken)
    state = _run(nodes)
    assert state["status"] == ("error" if isinstance(exc, RuntimeError) else "refused")
    assert state["metrics"]["schema_retry"]["triggered"] is False
    assert calls["retrieve_modes"] == ["neo4j"]


def test_switch_off_refuses_without_retry() -> None:
    nodes, calls = _nodes("not_answerable")
    state = _run(nodes, enable_schema_retry=False)
    assert state["status"] == "refused" and calls["retrieve_modes"] == ["neo4j"]
    assert state["metrics"]["schema_retry"]["triggered"] is False


def test_trace_event_record_field_and_json_round_trip() -> None:
    nodes, _ = _nodes("semantic_unanswerable")
    state = _run(nodes)
    (event,) = _events(state, "schema_retry")
    assert event["status"] == "retry" and event["reason"] == "Revenue is not in the schema."
    record = to_stakeholder_record("E3", QUESTION, state, model="m", provider_name="p",
                                   prompt_tokens=None, completion_tokens=None)
    assert record["qm_schema_retry"] == state["metrics"]["schema_retry"]
    assert json.loads(json.dumps(state)) == state


def test_ablation_has_schema_retry_variant_only_in_experiments() -> None:
    assert experiment_variants()["without_schema_retry"]["enable_schema_retry"] is False
    assert experiment_variants()["without_schema_retry"]["schema_mode"] == "neo4j"
    assert all("enable_schema_retry" not in flags for flags in ablation_variants().values())
