"""Cross-branch regressions using real routing, verifiers and offline providers."""

import json

from src.optimizer import optimize_sql
from src.orchestrator import run_querymind


class ScriptedProvider:
    """Exercise the shared live-provider boundary without network access."""

    def __init__(self):
        self.llm_calls = 0

    def generate(self, question, context):
        self.llm_calls += 1
        if "semantic verifier" in context:
            return json.dumps({"matches_question": True, "answerable": True, "reason": "Count matches."})
        if "result verifier" in context:
            return json.dumps({"plausible": True, "reason": "Scalar count."})
        return "SELECT COUNT(*) AS customer_count FROM customers"


def test_shared_provider_covers_generation_and_both_judges(db_path):
    provider = ScriptedProvider()
    state = run_querymind("How many customers are there?", schema_mode="flat", db_path=db_path, provider=provider)
    assert state["status"] == "success"
    assert state["semantic_ok"] and state["result_ok"]
    assert state["metrics"]["generation_calls"] == 1
    assert state["metrics"]["llm_calls"] == provider.llm_calls == 3


def test_missing_cost_refuses_before_execution_with_real_semantics(db_path):
    state = run_querymind("What is the profit margin per category?", db_path=db_path, provider=ScriptedProvider())
    assert state["status"] == "refused"
    assert "cost" in " ".join(state["missing_fields"])
    assert state["repair_count"] == 0
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_generator_refusal_preserves_fields_without_repair(db_path):
    class MissingProvider:
        is_mock = True

        def generate(self, question, context):
            return "NOT_ANSWERABLE:cost, category"

    state = run_querymind("Profit margin?", db_path=db_path, provider=MissingProvider())
    assert state["status"] == "refused"
    assert state["missing_fields"] == ["cost", "category"]
    assert state["repair_count"] == 0
    assert state["metrics"]["llm_calls"] == 0
    assert not any(event["node"] == "executor" for event in state["trace"])


def test_optimizer_trigger_stays_offline_with_mock_provider(db_path):
    sql = "SELECT name FROM customers WHERE customer_id IN (SELECT customer_id FROM orders)"
    result = optimize_sql(sql, "Customers with orders", "", db_path=db_path)
    assert not result["changed"]
    assert result["sql"] == sql
    assert result["llm_calls"] == 0
    assert "offline" in result["reason"]


def test_retrieval_reports_actual_tables_and_join_paths(db_path):
    state = run_querymind("Who are the top 3 customers by total spending?", schema_mode="flat", db_path=db_path)
    assert state["status"] == "success"
    assert {"customers", "orders"}.issubset(state["metrics"]["retrieved_tables"])
    assert "customers.customer_id = orders.customer_id" in state["metrics"]["retrieved_join_paths"]
    assert state["metrics"]["retrieval"]["backend"] == "flat"
