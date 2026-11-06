"""Offline schema retrieval contracts, including the explicit graph fallback."""

import json
from pathlib import Path
import sqlite3

import pytest

from scripts.seed_db import seed_database
from src.schema import FlatSchemaRetriever, Neo4jSchemaRetriever, retrieve_schema
from src.schema.build_graph import build_schema_graph


@pytest.fixture
def database(tmp_path):
    return seed_database(tmp_path / "analytics.db")


def test_flat_retriever_returns_schema_string(database):
    context = FlatSchemaRetriever(database).retrieve("top customers")
    assert isinstance(context, str)
    assert "TABLE customers" in context
    assert "REFERENCES customers(customer_id)" in context


def test_neo4j_mode_is_explicit_offline_fallback(database):
    context = Neo4jSchemaRetriever(database).retrieve("top customers")
    assert "starter placeholder" in context
    assert "TABLE orders" in context
    assert retrieve_schema("top customers", "neo4j", db_path=database) == context


def test_retrieval_rejects_invalid_mode_and_limit(database):
    with pytest.raises(ValueError):
        retrieve_schema("question", "unknown", db_path=database)
    with pytest.raises(ValueError):
        FlatSchemaRetriever(database).retrieve("question", top_k=0)


def test_graph_payload_is_serializable_without_neo4j(database):
    payload = build_schema_graph(database)
    json.dumps(payload)
    assert payload["status"] == "offline_payload_only"
    assert payload["relationships"][0]["to_table"] == "customers"


@pytest.fixture
def graph_database(tmp_path: Path) -> Path:
    """A join chain with a disconnected table and a non-FK index."""
    path = tmp_path / "join_chain.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(customer_id)
            );
            CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT);
            CREATE TABLE order_items (
                item_id INTEGER PRIMARY KEY,
                order_id INTEGER REFERENCES orders(order_id),
                product_id INTEGER REFERENCES products(product_id)
            );
            CREATE INDEX item_product_order ON order_items(product_id, order_id);
            CREATE TABLE offices (office_id INTEGER PRIMARY KEY, region TEXT);
        """)
    return path


@pytest.fixture
def quoted_database(tmp_path: Path) -> Path:
    """Composite implicit FK targets and SQL-quoted identifiers."""
    path = tmp_path / "quoted.db"
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE "parent ""records" (
                "part a" TEXT NOT NULL,
                "part b" INTEGER NOT NULL,
                description TEXT,
                PRIMARY KEY ("part a", "part b")
            );
            CREATE TABLE "child records" (
                id INTEGER PRIMARY KEY,
                "parent a" TEXT,
                "parent b" INTEGER,
                FOREIGN KEY ("parent a", "parent b") REFERENCES "parent ""records"
            );
            CREATE UNIQUE INDEX "unique ""description" ON "parent ""records" (description);
        ''')
    return path


def test_graph_records_primary_key_positions_and_indexes(graph_database: Path) -> None:
    payload = build_schema_graph(graph_database)
    tables = {table["name"]: table for table in payload["tables"]}
    identifier = next(column for column in tables["customers"]["columns"] if column["name"] == "customer_id")
    assert identifier["primary_key"] is True
    assert identifier["pk_position"] == 1
    index = next(index for index in tables["order_items"]["indexes"] if index["name"] == "item_product_order")
    assert index["columns"] == ["product_id", "order_id"]
    assert index["unique"] is False
    assert index["origin"] == "c"
    assert index["partial"] is False


def test_graph_resolves_composite_implicit_primary_key_targets(quoted_database: Path) -> None:
    payload = build_schema_graph(quoted_database)
    tables = {table["name"]: table for table in payload["tables"]}
    assert 'parent "records' in tables
    parent = tables['parent "records']
    positions = {column["name"]: column["pk_position"] for column in parent["columns"]}
    assert positions["part a"] == 1 and positions["part b"] == 2
    relationships = sorted(payload["relationships"], key=lambda relationship: relationship["sequence"])
    assert [relationship["from_column"] for relationship in relationships] == ["parent a", "parent b"]
    assert [relationship["to_column"] for relationship in relationships] == ["part a", "part b"]
    assert {relationship["to_table"] for relationship in relationships} == {'parent "records'}
    assert len({relationship["constraint_id"] for relationship in relationships}) == 1
    assert any(index["name"] == 'unique "description' and index["unique"] for index in parent["indexes"])
    json.dumps(payload)


def test_graph_namespaces_identical_schema_for_separate_databases(database: Path) -> None:
    first = build_schema_graph(database, database_id="tenant_a")
    second = build_schema_graph(database, database_id="tenant_b")
    assert first["schema_fingerprint"] == second["schema_fingerprint"]
    assert first["database_id"] != second["database_id"]
    assert first["schema_id"] != second["schema_id"]


def test_schema_fingerprint_ignores_rows_but_tracks_schema(graph_database: Path) -> None:
    initial = build_schema_graph(graph_database)
    with sqlite3.connect(graph_database) as connection:
        connection.execute("INSERT INTO customers VALUES (1, 'Ada')")
    with_rows = build_schema_graph(graph_database)
    assert initial["schema_fingerprint"] == with_rows["schema_fingerprint"]
    assert initial["schema_id"] == with_rows["schema_id"]
    with sqlite3.connect(graph_database) as connection:
        connection.execute("ALTER TABLE customers ADD COLUMN email TEXT")
    changed = build_schema_graph(graph_database)
    assert changed["database_id"] == initial["database_id"]
    assert changed["schema_fingerprint"] != initial["schema_fingerprint"]


def test_flat_metadata_describes_full_schema(graph_database: Path) -> None:
    retriever = FlatSchemaRetriever(graph_database)
    result = retriever.retrieve_with_metadata("customers products", top_k=2)
    assert result.backend == "flat"
    assert set(result.tables) == {"customers", "orders", "order_items", "products", "offices"}
    assert "customers.customer_id" in result.columns
    assert result.latency_ms >= 0
    assert result.schema_id == build_schema_graph(graph_database)["schema_id"]
    assert retriever.retrieve("customers products", top_k=2) == result.context


def test_local_graph_includes_intermediate_join_tables(graph_database: Path) -> None:
    result = Neo4jSchemaRetriever(graph_database, backend="local_graph").retrieve_with_metadata(
        "customers products", top_k=2
    )
    assert result.backend == "local_graph"
    assert set(result.tables) == {"customers", "orders", "order_items", "products"}
    assert len(result.relationships) == 3
    assert "TABLE offices" not in result.context
    assert "orders.customer_id" in result.columns
    assert result.latency_ms >= 0


def test_local_graph_ranks_column_names(graph_database: Path) -> None:
    result = Neo4jSchemaRetriever(graph_database, backend="local_graph").retrieve_with_metadata(
        "Which region?", top_k=1
    )
    assert result.tables == ["offices"]
    assert "offices.region" in result.columns


def test_local_graph_handles_disconnected_matching_tables(graph_database: Path) -> None:
    result = Neo4jSchemaRetriever(graph_database, backend="local_graph").retrieve_with_metadata(
        "customers offices", top_k=2
    )
    assert set(result.tables) == {"customers", "offices"}
    assert result.relationships == []


def test_unrelated_question_gets_explicit_full_schema_fallback(graph_database: Path) -> None:
    result = Neo4jSchemaRetriever(graph_database, backend="local_graph").retrieve_with_metadata(
        "weather forecasts tomorrow", top_k=1
    )
    assert set(result.tables) == {"customers", "orders", "order_items", "products", "offices"}
    assert result.context
    assert result.fallback_reason
    assert result.backend == "local_graph"


def test_neo4j_fallback_metadata_does_not_claim_graph_backend(database: Path, monkeypatch) -> None:
    for key in ("NEO4J_URI", "NEO4J_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    result = Neo4jSchemaRetriever(database).retrieve_with_metadata("top customers")
    assert result.backend == "flat_fallback"
    assert "starter placeholder" in result.context
    assert result.fallback_reason


def test_neo4j_missing_password_never_requires_network(database: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    result = Neo4jSchemaRetriever(database).retrieve_with_metadata("top customers")
    assert result.backend == "flat_fallback"
    assert result.fallback_reason


def test_local_graph_retrieval_is_deterministic(graph_database: Path) -> None:
    retriever = Neo4jSchemaRetriever(graph_database, backend="local_graph")
    first = retriever.retrieve_with_metadata("customers products", top_k=2)
    second = retriever.retrieve_with_metadata("customers products", top_k=2)
    assert first.context == second.context
    assert first.tables == second.tables
    assert first.columns == second.columns
    assert first.relationships == second.relationships


class _UnavailableDriver:
    """Exercise availability handling without constructing a real driver."""

    def session(self, **kwargs):
        raise RuntimeError("offline simulated graph outage")


def test_graph_outage_falls_back_explicitly(database: Path) -> None:
    result = Neo4jSchemaRetriever(database, driver=_UnavailableDriver()).retrieve_with_metadata(
        "top customers"
    )
    assert result.backend == "flat_fallback"
    assert "Neo4j retrieval failed" in result.fallback_reason
    assert "offline simulated graph outage" not in result.fallback_reason
    assert "TABLE customers" in result.context


def test_strict_graph_outage_is_not_silently_fallback(database: Path) -> None:
    retriever = Neo4jSchemaRetriever(database, driver=_UnavailableDriver(), strict=True)
    with pytest.raises(RuntimeError, match="Neo4j retrieval failed") as error:
        retriever.retrieve_with_metadata("top customers")
    assert "offline simulated graph outage" in str(error.value.__cause__)


class _Records(list):
    def consume(self) -> None:
        return None


class _RecordingTransaction:
    """Record Cypher parameters and return graph-shaped fixture records."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        payload = self.payload
        if "RETURN properties(s) AS schema" in query:
            return _Records([] if payload is None else [{"schema": {
                key: payload[key] for key in ("database_id", "schema_fingerprint", "schema_id")
            }}])
        if payload is None:
            return _Records()
        if "RETURN properties(t) AS table" in query:
            return _Records({"table": {"name": table["name"], "sql": table["sql"]}} for table in payload["tables"])
        if "RETURN properties(c) AS column" in query:
            return _Records({"column": {**column, "table_name": table["name"], "schema_id": payload["schema_id"]}}
                            for table in payload["tables"] for column in table["columns"])
        if "RETURN properties(i) AS index" in query:
            return _Records({"index": {**index, "table_name": table["name"], "schema_id": payload["schema_id"]}}
                            for table in payload["tables"] for index in table["indexes"])
        if "properties(r) AS metadata" in query:
            endpoint_keys = ("from_table", "from_column", "to_table", "to_column")
            return _Records({**{key: relationship[key] for key in endpoint_keys},
                             "metadata": {key: value for key, value in relationship.items() if key not in endpoint_keys}}
                            for relationship in payload["relationships"])
        if "RETURN DISTINCT table_name" in query:
            return _Records([{"table_name": "orders"}, {"table_name": "order_items"}])
        return _Records()


class _RecordingSession:
    def __init__(self, transaction):
        self.transaction = transaction

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute_write(self, callback):
        return callback(self.transaction)

    def execute_read(self, callback):
        return callback(self.transaction)


class _RecordingDriver:
    def __init__(self, payload):
        self.transaction = _RecordingTransaction(payload)
        self.session_options = []

    def session(self, **kwargs):
        self.session_options.append(kwargs)
        return _RecordingSession(self.transaction)


def test_graph_upload_parameterizes_names_and_uses_repeatable_merge(quoted_database: Path) -> None:
    from src.schema.neo4j_store import upload_schema_graph

    payload = build_schema_graph(quoted_database, database_id="quoted_namespace")
    driver = _RecordingDriver(payload)
    first = upload_schema_graph(payload, driver=driver, database="schema_catalog")
    first_calls = list(driver.transaction.calls)
    second = upload_schema_graph(payload, driver=driver, database="schema_catalog")
    assert first == second
    assert first["schema_id"] == payload["schema_id"]
    assert first["references"] == 2
    assert first_calls == driver.transaction.calls[len(first_calls):]
    assert driver.session_options == [{"database": "schema_catalog"}, {"database": "schema_catalog"}]
    for query, parameters in first_calls:
        assert "MERGE" in query
        assert "DELETE" not in query
        assert 'parent "records' not in query
        assert "quoted_namespace" not in query
        assert parameters["schema_id"] == payload["schema_id"]


def test_graph_load_round_trips_metadata_without_sdk_or_server(quoted_database: Path) -> None:
    from src.schema.neo4j_store import load_schema_graph

    payload = build_schema_graph(quoted_database)
    driver = _RecordingDriver(payload)
    loaded = load_schema_graph(driver=driver, schema_id=payload["schema_id"])
    assert loaded["status"] == "loaded_from_neo4j"
    for key in ("database_id", "schema_id", "schema_fingerprint", "tables", "relationships"):
        assert loaded[key] == payload[key]
    assert all(parameters["schema_id"] == payload["schema_id"] for _, parameters in driver.transaction.calls)


def test_graph_load_missing_schema_is_explicit() -> None:
    from src.schema.neo4j_store import load_schema_graph

    with pytest.raises(LookupError, match="not been uploaded"):
        load_schema_graph(driver=_RecordingDriver(None), schema_id="missing:version")


def test_native_join_path_query_is_scoped_and_preserves_seeds(graph_database: Path) -> None:
    from src.schema.neo4j_store import expand_join_paths

    payload = build_schema_graph(graph_database)
    driver = _RecordingDriver(payload)
    tables = expand_join_paths(
        driver=driver, schema_id=payload["schema_id"],
        table_names=["products", "customers", "customers", "offices"],
    )
    assert tables == ["customers", "offices", "order_items", "orders", "products"]
    query, parameters = driver.transaction.calls[0]
    assert "shortestPath" in query and "HAS_COLUMN|REFERENCES" in query
    assert "ELSE node.table_name" in query
    assert parameters["schema_id"] == payload["schema_id"]
    assert parameters["table_names"] == ["customers", "offices", "products"]
    assert "node.schema_id = $schema_id" in query


def test_upload_refuses_dangling_foreign_keys_before_graph_writes(database: Path) -> None:
    from src.schema.neo4j_store import upload_schema_graph

    payload = build_schema_graph(database)
    payload["relationships"][0]["to_column"] = "missing_column"
    driver = _RecordingDriver(payload)
    with pytest.raises(ValueError, match="unresolved"):
        upload_schema_graph(payload, driver=driver)
    assert driver.session_options == []


def test_mocked_live_graph_retriever_uses_native_join_paths(graph_database: Path) -> None:
    payload = build_schema_graph(graph_database)
    driver = _RecordingDriver(payload)
    result = Neo4jSchemaRetriever(
        graph_database, driver=driver, database="schema_catalog", strict=True
    ).retrieve_with_metadata("customers products", top_k=2)
    assert result.backend == "neo4j"
    assert not result.fallback_reason
    assert set(result.tables) == {"customers", "orders", "order_items", "products"}
    assert len(result.relationships) == 3
    assert any("shortestPath" in query for query, _ in driver.transaction.calls)
    assert all(options == {"database": "schema_catalog"} for options in driver.session_options)


def test_expression_indexes_preserve_expression_and_column_positions(graph_database: Path) -> None:
    with sqlite3.connect(graph_database) as connection:
        connection.execute("CREATE INDEX customer_search ON customers(lower(name), customer_id, length(name))")
    payload = build_schema_graph(graph_database)
    table = next(table for table in payload["tables"] if table["name"] == "customers")
    index = next(index for index in table["indexes"] if index["name"] == "customer_search")
    assert index["columns"] == ["customer_id"]
    assert index["column_positions"] == [1]
    assert index["expression_positions"] == [0, 2]
    flat = FlatSchemaRetriever(graph_database).retrieve_with_metadata("customers")
    graph = Neo4jSchemaRetriever(graph_database, backend="local_graph").retrieve_with_metadata("customers", top_k=1)
    expected_index = "CREATE INDEX customer_search ON customers(lower(name), customer_id, length(name))"
    assert expected_index in flat.context
    assert expected_index in graph.context
    from src.schema.context import render_schema

    index["sql"] = None
    assert "INDEX customer_search ON customers (<expression>, customer_id, <expression>)" in render_schema(payload, ["customers"])


@pytest.mark.parametrize("mode", ["flat", "local_graph"])
def test_failed_retrieval_clears_previous_instrumentation(graph_database: Path, mode: str) -> None:
    retriever = (FlatSchemaRetriever(graph_database) if mode == "flat"
                 else Neo4jSchemaRetriever(graph_database, backend="local_graph"))
    result = retriever.retrieve_with_metadata("customers", top_k=1)
    assert retriever.last_result is result
    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("customers", top_k=0)
    assert retriever.last_result is None


def test_graph_fallback_replaces_prior_live_provenance(graph_database: Path) -> None:
    payload = build_schema_graph(graph_database)
    retriever = Neo4jSchemaRetriever(graph_database, driver=_RecordingDriver(payload))
    live = retriever.retrieve_with_metadata("customers products", top_k=2)
    assert live.backend == "neo4j" and "offices" not in live.tables
    retriever.driver = _UnavailableDriver()
    fallback = retriever.retrieve_with_metadata("customers products", top_k=2)
    assert retriever.last_result is fallback
    assert fallback.backend == "flat_fallback"
    assert fallback.metrics["backend"] == "flat_fallback"
    assert fallback.schema_id == live.schema_id
    assert fallback.fallback_reason and "offices" in fallback.tables


def test_strict_graph_failure_clears_prior_live_provenance(graph_database: Path) -> None:
    payload = build_schema_graph(graph_database)
    retriever = Neo4jSchemaRetriever(graph_database, driver=_RecordingDriver(payload), strict=True)
    assert retriever.retrieve_with_metadata("customers products", top_k=2).backend == "neo4j"
    retriever.driver = _UnavailableDriver()
    with pytest.raises(RuntimeError, match="Neo4j retrieval failed"):
        retriever.retrieve_with_metadata("customers products", top_k=2)
    assert retriever.last_result is None
