"""Offline experiment controls, source provenance and retrieval metric tests."""

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from src.schema.spider_cases import load_cases, select_spider_cases
from src.schema.spider_metrics import count_context_tokens, retrieval_metrics


@pytest.fixture
def spider_dataset(tmp_path: Path) -> Path:
    """A synthetic Spider-format fixture, never reported as benchmark evidence."""
    root = tmp_path / "synthetic_spider"
    database_dir = root / "database" / "demo"
    database_dir.mkdir(parents=True)
    with sqlite3.connect(database_dir / "demo.sqlite") as connection:
        connection.executescript("""
            CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(customer_id));
            CREATE TABLE order_items (item_id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(order_id), amount REAL);
            INSERT INTO customers VALUES (1, 'Ada'), (2, 'Ben');
            INSERT INTO orders VALUES (10, 1), (11, 2);
            INSERT INTO order_items VALUES (100, 10, 12), (101, 10, 8), (102, 11, 4);
        """)
    schema = {
        "db_id": "demo", "table_names_original": ["customers", "orders", "order_items"],
        "table_names": ["customers", "orders", "order items"],
        "column_names_original": [[-1, "*"], [0, "customer_id"], [0, "name"], [1, "order_id"],
                                  [1, "customer_id"], [2, "item_id"], [2, "order_id"], [2, "amount"]],
        "column_types": ["text", "number", "text", "number", "number", "number", "number", "number"],
        "primary_keys": [1, 3, 5], "foreign_keys": [[4, 1], [6, 3]],
    }
    schema["column_names"] = schema["column_names_original"]
    first_join = [False, 2, [0, [0, 1, False], None], [0, 4, False], None]
    second_join = [False, 2, [0, [0, 3, False], None], [0, 6, False], None]
    common = {"where": [], "groupBy": [[0, 2, False]], "having": [], "orderBy": [],
              "limit": None, "intersect": None, "union": None, "except": None}
    bridge_ast = {
        **common,
        "select": [False, [[0, [0, [0, 2, False], None]], [4, [0, [0, 7, False], None]]]],
        "from": {"table_units": [["table_unit", 0], ["table_unit", 1], ["table_unit", 2]],
                 "conds": [first_join, "and", second_join]},
    }
    count_ast = {
        **deepcopy(common),
        "select": [False, [[0, [0, [0, 2, False], None]], [3, [0, [0, 0, False], None]]]],
        "from": {"table_units": [["table_unit", 0], ["table_unit", 1]], "conds": [first_join]},
    }
    questions = [
        {"db_id": "demo", "question": "Show customers and their total order item amount.",
         "query": "SELECT customers.name, SUM(order_items.amount) FROM customers JOIN orders ON customers.customer_id = orders.customer_id JOIN order_items ON orders.order_id = order_items.order_id GROUP BY customers.name",
         "sql": bridge_ast},
        {"db_id": "demo", "question": "Show customers and their number of orders.",
         "query": "SELECT customers.name, COUNT(*) FROM customers JOIN orders ON customers.customer_id = orders.customer_id GROUP BY customers.name",
         "sql": count_ast},
    ]
    (root / "tables.json").write_text(json.dumps([schema]), encoding="utf-8")
    (root / "dev.json").write_text(json.dumps(questions), encoding="utf-8")
    return root


def test_case_selection_is_deterministic_and_records_sources(spider_dataset: Path, tmp_path: Path) -> None:
    first = select_spider_cases(spider_dataset, count=2)
    assert first == select_spider_cases(spider_dataset, count=2)
    assert len(first["cases"]) == 2
    assert any(case["requires_bridge"] for case in first["cases"])
    assert any(case["has_aggregation"] for case in first["cases"])
    assert first["source_files"]["dev.json"]["sha256"]
    assert first["source_files"]["tables.json"]["sha256"]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(first), encoding="utf-8")
    assert load_cases(path) == first


def test_gold_join_annotations_include_each_bridge_edge(spider_dataset: Path) -> None:
    manifest = select_spider_cases(spider_dataset, count=2)
    bridge = next(case for case in manifest["cases"] if case["requires_bridge"])
    assert set(bridge["required_tables"]) == {"customers", "orders", "order_items"}
    assert len(bridge["required_joins"]) == 2
    assert "customers.name" in bridge["required_columns"]
    assert "order_items.amount" in bridge["required_columns"]


def test_retrieval_metrics_do_not_reward_duplicate_or_unrelated_context() -> None:
    edge = {"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id"}
    reverse = {"from_table": "CUSTOMERS", "from_column": "CUSTOMER_ID", "to_table": "ORDERS", "to_column": "CUSTOMER_ID"}
    result = retrieval_metrics(
        ["customers", "orders"], ["customers.name"], [edge],
        ["customers", "CUSTOMERS", "orders", "offices"], ["customers.name", "offices.region"], [edge, reverse],
    )
    assert result["tables"]["recall"] == 1.0
    assert result["tables"]["precision"] == pytest.approx(2 / 3)
    assert result["tables"]["exact_set"] is False
    assert result["columns"]["precision"] == 0.5
    assert result["joins"]["retrieved_count"] == 1
    assert result["join_path_covered"] is True


def test_join_path_metric_requires_every_bridge_edge() -> None:
    first = {"from_table": "a", "from_column": "id", "to_table": "b", "to_column": "a_id"}
    second = {"from_table": "b", "from_column": "id", "to_table": "c", "to_column": "b_id"}
    result = retrieval_metrics(["a", "b", "c"], [], [first, second], ["a", "b", "c"], [], [first])
    assert result["tables"]["recall"] == 1.0
    assert result["joins"]["recall"] == 0.5
    assert result["join_path_covered"] is False


def test_token_counts_label_estimates_and_allow_explicit_tokenizer() -> None:
    estimated = count_context_tokens("TABLE customers (id INTEGER)")
    assert estimated["is_estimate"] is True and estimated["count"] > 0
    exact = count_context_tokens("example", tokenizer=lambda context: 7)
    assert exact == {"count": 7, "method": "configured_tokenizer", "is_estimate": False}
    with pytest.raises(ValueError):
        count_context_tokens("example", tokenizer=lambda context: -1)


def test_retrieval_only_diagnostic_has_no_execution_accuracy(spider_dataset: Path, monkeypatch, tmp_path: Path) -> None:
    from src.schema import spider_experiment

    def forbid_execution(*args, **kwargs):
        raise AssertionError("Retrieval-only diagnostics must not execute reference or generated SQL")

    monkeypatch.setattr(spider_experiment, "execute_sql", forbid_execution)
    cases = select_spider_cases(spider_dataset, count=2)
    report = spider_experiment.run_schema_experiment(spider_dataset, cases, repetitions=2)
    assert report["manifest"]["backend"] == "local_graph"
    assert report["manifest"]["diagnostic"] is True
    assert report["manifest"]["live_neo4j_measured"] is False
    assert report["manifest"]["generation_enabled"] is False
    assert report["manifest"]["controls"]["gold_passed_to_retriever_or_generator"] is False
    assert all(setup["upload"] is None for setup in report["graph_setup"])
    for arm in ("flat", "graph"):
        assert report["summary"][arm]["result_accuracy"] is None
        assert report["summary"][arm]["execution_success_rate"] is None
        assert report["summary"][arm]["generation_attempts"] == 0
    for case in report["cases"]:
        assert case["retrieval_orders"][0] == list(reversed(case["retrieval_orders"][1]))
        for arm in case["arms"].values():
            assert arm["generation"] is None
            assert len(arm["retrieval_latencies_ms"]) == 2
            assert arm["metadata_stable_across_repetitions"] is True
    json_path, markdown_path = spider_experiment.write_report(report, tmp_path / "diagnostic.json")
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "offline diagnostic" in markdown
    assert "TBD" in markdown


class _RecordingProvider:
    """Integration-test double; never used for committed benchmark reports."""

    model = "unit-test-double"
    temperature = 0

    def __init__(self, sql: str = "SELECT 0 AS value") -> None:
        self.calls: list[tuple[str, str]] = []
        self.sql = sql

    def generate(self, question: str, schema_context: str) -> str:
        self.calls.append((question, schema_context))
        return self.sql


def test_generation_uses_same_provider_and_receives_no_gold(spider_dataset: Path) -> None:
    from src.schema.spider_experiment import run_schema_experiment

    cases = select_spider_cases(spider_dataset, count=2)
    provider = _RecordingProvider()
    report = run_schema_experiment(
        spider_dataset, cases, repetitions=2, provider=provider,
        provider_name="unit-test-double", model=provider.model, temperature=0,
    )
    assert len(provider.calls) == 4
    assert report["manifest"]["provider"] == "unit-test-double"
    assert report["manifest"]["model"] == provider.model
    assert report["manifest"]["controls"]["same_provider_instance"] is True
    for case in cases["cases"]:
        received = [context for question, context in provider.calls if question == case["question"]]
        assert len(received) == 2
        assert all(case["reference_sql"] not in context for context in received)
    for measured in report["cases"]:
        for arm in measured["arms"].values():
            outcome = arm["generation"]
            assert outcome["sql"] == "SELECT 0 AS value"
            assert outcome["execution_ok"] is True
            assert outcome["result_correct"] is False
    assert report["summary"]["graph"]["result_accuracy"] == 0.0


def test_generated_mutation_is_rejected_without_changing_database(spider_dataset: Path) -> None:
    from src.schema.spider_cases import file_sha256
    from src.schema.spider_experiment import render_markdown, run_schema_experiment

    cases = select_spider_cases(spider_dataset, count=2)
    database = spider_dataset / "database" / "demo" / "demo.sqlite"
    original_hash = file_sha256(database)
    provider = _RecordingProvider("DELETE FROM customers")
    report = run_schema_experiment(spider_dataset, cases, provider=provider, provider_name="unit-test-double")
    assert file_sha256(database) == original_hash
    for case in report["cases"]:
        for arm in case["arms"].values():
            assert arm["generation"]["sql_generated"] is True
            assert arm["generation"]["syntax_ok"] is False
            assert arm["generation"]["execution_ok"] is False
            assert arm["generation"]["result_correct"] is False
    markdown = render_markdown(report)
    assert "no successful executions" in markdown
    assert "generation disabled" not in markdown


def test_experiment_rejects_changed_source_or_gold_annotations(spider_dataset: Path) -> None:
    from src.schema.spider_experiment import run_schema_experiment

    cases = select_spider_cases(spider_dataset, count=2)
    stale_annotations = deepcopy(cases)
    stale_annotations["cases"][0]["required_tables"] = ["invented_table"]
    with pytest.raises(ValueError, match="annotations differ"):
        run_schema_experiment(spider_dataset, stale_annotations)
    path = spider_dataset / "dev.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint differs"):
        run_schema_experiment(spider_dataset, cases)


def test_experiment_refuses_mock_or_mismatched_generation_controls(spider_dataset: Path) -> None:
    from src.llm import MockProvider
    from src.schema.spider_experiment import run_schema_experiment

    cases = select_spider_cases(spider_dataset, count=2)
    with pytest.raises(ValueError, match="Mock/oracle"):
        run_schema_experiment(spider_dataset, cases, provider=MockProvider())
    provider = _RecordingProvider()
    with pytest.raises(ValueError, match="temperature"):
        run_schema_experiment(spider_dataset, cases, provider=provider, temperature=1)
    with pytest.raises(ValueError, match="model"):
        run_schema_experiment(spider_dataset, cases, provider=provider, model="different-model")
