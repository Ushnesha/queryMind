"""R6: compact answer-writer evidence, a completion cap, and per-step time/tokens in traces."""

from dataclasses import replace
import json

from src.agents.response import RESPONSE_MAX_TOKENS, SAMPLE_ROWS, generate_response, summarize_result
from src.config import Settings
from src.evaluation.stakeholder import to_stakeholder_record
from src.orchestrator import Components, run_querymind, summarize_node_usage

MONTHS = [[f"2024-{m:02d}", float(m * 100)] for m in range(1, 13)]


def test_summary_has_count_totals_peak_and_label_range() -> None:
    summary = summarize_result(["month", "revenue"], MONTHS)
    assert summary["row_count"] == 12
    assert summary["column_stats"]["revenue"] == {"min": 100.0, "max": 1200.0, "total": 7800.0,
                                                  "mean": 650.0, "non_null": 12}
    assert summary["column_stats"]["month"]["first"] == "2024-01"
    assert summary["column_stats"]["month"]["last"] == "2024-12"
    assert summary["peak_row"] == {"month": "2024-12", "revenue": 1200.0}
    assert summary["lowest_row"] == {"month": "2024-01", "revenue": 100.0}
    json.dumps(summary, allow_nan=False)


def test_summary_ignores_nulls_and_mixed_columns() -> None:
    summary = summarize_result(["name", "value"], [["a", 1], ["b", None], [None, 3]])
    assert summary["column_stats"]["value"]["non_null"] == 2
    assert summary["peak_row"]["value"] == 3
    assert summarize_result(["x"], [[1]]).get("peak_row") is None  # single row: nothing to rank


def test_answer_writer_gets_summary_sample_and_token_cap() -> None:
    seen = {}

    class Provider:
        def generate(self, question, context, *, max_tokens=None):
            seen.update(context=context, max_tokens=max_tokens)
            return "Revenue rose every month, peaking at 1200 in December."

    rows = MONTHS * 20  # 240 rows, like Milestone 2's slow H1 answer
    state = {"question": "Show sales trends over time.", "status": "success", "answerable": True,
             "sql": "SELECT 1", "columns": ["month", "revenue"], "rows": rows, "metrics": {}}
    assert generate_response(state, provider=Provider()).startswith("Revenue rose")
    assert seen["max_tokens"] == RESPONSE_MAX_TOKENS
    evidence = json.loads(seen["context"].split("Executed result:\n", 1)[1])
    assert len(evidence["rows"]) == SAMPLE_ROWS and evidence["sample_truncated"] is True
    assert evidence["summary"]["row_count"] == 240
    assert "Do NOT list or describe every row" in seen["context"]
    assert state["metrics"]["response_generation"] == {"mode": "model", "max_tokens": RESPONSE_MAX_TOKENS,
                                                       "rows_sent": SAMPLE_ROWS, "row_count": 240}


def test_providers_without_max_tokens_still_work() -> None:
    class Provider:
        def generate(self, question, context):
            return "Twelve months of revenue."

    state = {"question": "q", "status": "success", "answerable": True, "sql": "SELECT 1",
             "columns": ["month", "revenue"], "rows": MONTHS, "metrics": {}}
    assert generate_response(state, provider=Provider()) == "Twelve months of revenue."
    assert state["metrics"]["response_generation"]["max_tokens"] is None


class CountingProvider:
    """Live-provider stand-in with the OpenAI-compatible counters."""

    def __init__(self, sql: str) -> None:
        self.sql, self.llm_calls, self.prompt_tokens, self.completion_tokens = sql, 0, 0, 0

    def generate(self, question, context, *, max_tokens=None):
        self.llm_calls += 1
        self.prompt_tokens += 100
        if "answer writer" in context:
            self.completion_tokens += 7
            return "There are 3 customers."
        self.completion_tokens += 20
        return self.sql


def test_trace_records_time_and_tokens_per_step(db_path) -> None:
    provider = CountingProvider("SELECT name FROM customers ORDER BY customer_id LIMIT 3")
    nodes = replace(
        Components(),
        verify_semantics=lambda *a, **k: {"matches_question": True, "answerable": True, "reason": "ok",
                                          "missing_fields": [], "assumptions": []},
        verify_result=lambda *a, **k: {"ok": True, "warnings": [], "statistics": {}},
    )
    state = run_querymind("List three customers.", schema_mode="flat", db_path=db_path, provider=provider,
                          settings=Settings(), components=nodes)
    assert state["status"] == "success", state["error"]
    (generation,) = [e for e in state["trace"] if e["node"] == "sql_generator"]
    assert (generation["llm_calls"], generation["prompt_tokens"], generation["completion_tokens"]) == (1, 100, 20)
    response = [e for e in state["trace"] if e["node"] == "response_generator"][-1]
    assert (response["llm_calls"], response["completion_tokens"]) == (1, 7)
    # Nodes without model calls carry no usage fields.
    assert "llm_calls" not in [e for e in state["trace"] if e["node"] == "executor"][0]
    metrics = state["metrics"]
    assert set(metrics["node_latency_ms"]) >= {"schema_retriever", "sql_generator", "executor", "response_generator"}
    assert metrics["node_tokens"]["sql_generator"] == {"llm_calls": 1, "prompt_tokens": 100, "completion_tokens": 20}
    assert metrics["llm_calls"] == sum(item["llm_calls"] for item in metrics["node_tokens"].values())
    record = to_stakeholder_record("X", "List three customers.", state, model="m", provider_name="p",
                                   prompt_tokens=provider.prompt_tokens, completion_tokens=provider.completion_tokens)
    assert record["qm_node_tokens"] == metrics["node_tokens"]
    assert record["qm_node_latency_ms"] == metrics["node_latency_ms"]
    json.dumps(record, allow_nan=False)


def test_node_usage_sums_repeated_steps() -> None:
    trace = [
        {"node": "sql_generator", "latency_ms": 10.0, "llm_calls": 1, "prompt_tokens": 5, "completion_tokens": 2},
        {"node": "repair", "latency_ms": 0.0},
        {"node": "sql_generator", "latency_ms": 15.5, "llm_calls": 1, "prompt_tokens": 6, "completion_tokens": 3},
    ]
    latency, tokens = summarize_node_usage(trace)
    assert latency == {"sql_generator": 25.5, "repair": 0.0}
    assert tokens == {"sql_generator": {"llm_calls": 2, "prompt_tokens": 11, "completion_tokens": 5}}


def test_mock_runs_have_empty_token_summary(db_path) -> None:
    state = run_querymind("Who are the top 3 customers by total spending?", schema_mode="flat", db_path=db_path)
    assert state["metrics"]["node_tokens"] == {}
    assert state["metrics"]["node_latency_ms"]["executor"] >= 0
