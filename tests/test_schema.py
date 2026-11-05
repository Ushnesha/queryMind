"""Offline schema retrieval contracts, including the explicit graph fallback."""

import json

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
