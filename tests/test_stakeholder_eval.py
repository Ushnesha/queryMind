"""Stakeholder-format trace adapter and Spider pilot builder."""

import json
import sqlite3

import yaml

from scripts.build_spider_pilot import build, complexity
from src.evaluation.stakeholder import interpretation_assumptions, to_stakeholder_record


def _state(**overrides):
    state = {
        "status": "success", "sql": "SELECT 1", "sql_history": ["SELECT 1"], "rows": [[1]],
        "missing_fields": [], "assumptions": [], "semantic_reason": "ok", "error": "",
        "repair_count": 0, "optimizer_count": 1, "optimization_applied": False,
        "metrics": {"llm_calls": 4, "generation_calls": 1, "total_latency_ms": 1234.5,
                    "retrieval": {"backend": "neo4j", "fallback_reason": ""}},
        "trace": [{"node": "syntax_verifier", "status": "pass", "iteration": 1},
                  {"node": "executor", "status": "pass"}],
    }
    state.update(overrides)
    return state


def _record(state):
    return to_stakeholder_record("Q1", "question?", state, model="m", provider_name="opencode",
                                 prompt_tokens=10, completion_tokens=5)


def test_success_maps_to_executed_answer():
    record = _record(_state())
    assert record["exec_ok"] is True and record["refused"] is False
    assert record["latency_ms"] == 1234.5 and record["qm_llm_calls"] == 4
    assert record["qm_first_attempt_ok"] is True and record["qm_schema_fallback"] is False


def test_infrastructure_notes_earn_no_ambiguity_credit():
    notes = ["Schema retrieval note: x", "LLM semantic judge unavailable (timeout); deterministic checks only."]
    assert interpretation_assumptions(notes) == []
    record = _record(_state(assumptions=[*notes, "Best means top three by spending."]))
    assert record["assumptions"] == "Best means top three by spending."
    assert _record(_state(assumptions=notes))["assumptions"] is None


def test_missing_field_refusal_is_a_refusal():
    record = _record(_state(status="refused", sql="NOT_ANSWERABLE: product cost", missing_fields=["product cost"],
                            semantic_reason="Required data is missing: product cost", trace=[]))
    assert record["refused"] is True and record["missing_field"] == "product cost"
    assert record["exec_ok"] is False and record["error_type"] is None


def test_gateway_failure_is_not_counted_as_refusal():
    record = _record(_state(status="refused", semantic_reason="Provider network error: timed out", trace=[]))
    assert record["refused"] is False and record["error_type"] == "ProviderError"


def test_failed_result_verification_is_not_an_answer():
    record = _record(_state(status="error", error="Result structure failed verification."))
    assert record["exec_ok"] is False and record["error_type"] == "ResultVerificationFailed"


def test_repair_limit_is_labelled():
    record = _record(_state(status="refused", trace=[{"node": "syntax_verifier", "status": "fail", "iteration": 1}],
                            semantic_reason="SQL verification failed after the configured repair limit: x"))
    assert record["refused"] is True and record["error_type"] == "RepairLimitReached"
    assert record["qm_first_attempt_ok"] is False


def test_provider_accumulates_reported_token_usage():
    from src.llm import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider()
    provider._record_usage({"prompt_tokens": 100, "completion_tokens": 20})
    provider._record_usage({"prompt_tokens": 50, "completion_tokens": 5})
    provider._record_usage(None)
    assert (provider.prompt_tokens, provider.completion_tokens, provider.calls_without_usage) == (150, 25, 1)


def test_complexity_rule():
    assert complexity("SELECT name FROM singer") == "single"
    assert complexity("SELECT a FROM t JOIN u ON t.id = u.id") == "multi"
    assert complexity("SELECT a FROM t WHERE x IN (SELECT y FROM u)") == "multi"
    assert complexity("SELECT a FROM t EXCEPT SELECT a FROM u") == "multi"


def test_pilot_build_is_seeded_and_drops_empty_gold(tmp_path):
    root = tmp_path / "spider"
    (root / "database/toy").mkdir(parents=True)
    conn = sqlite3.connect(root / "database/toy/toy.sqlite")
    conn.executescript("CREATE TABLE t(a INTEGER); INSERT INTO t VALUES (1), (2);")
    conn.commit()
    conn.close()
    dev = [
        {"db_id": "toy", "question": "All a?", "query": "SELECT a FROM t ORDER BY a"},
        {"db_id": "toy", "question": "None?", "query": "SELECT a FROM t WHERE a > 9"},
        {"db_id": "toy", "question": "Broken?", "query": "SELECT nope FROM t"},
        {"db_id": "toy", "question": "Count?", "query": "SELECT count(*) FROM t;"},
    ]
    (root / "dev.json").write_text(json.dumps(dev))
    first = build(root, tmp_path / "out", size=2, seed=1)
    second = build(root, tmp_path / "out2", size=2, seed=1)
    assert first["databases"] == second["databases"] and first["selected"] == 2
    assert {d["reason"] for d in first["dropped"]} <= {"gold result is empty", "gold SQL error: no such column: nope"}
    items = yaml.safe_load((tmp_path / "out/questions/toy.yaml").read_text())
    assert {item["id"] for item in items} == {"S0000", "S0003"}
    ordered = {item["id"]: item["ordered"] for item in items}
    assert ordered == {"S0000": True, "S0003": False}
    assert all(not item["reference_sql"].strip().endswith(";") for item in items)
