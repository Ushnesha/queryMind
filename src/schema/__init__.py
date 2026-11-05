"""Stable public schema interfaces used by the orchestration layer."""

from pathlib import Path

from src.schema.flat_retriever import FlatSchemaRetriever
from src.schema.interface import SchemaRetriever
from src.schema.neo4j_retriever import Neo4jSchemaRetriever

__all__ = ["SchemaRetriever", "FlatSchemaRetriever", "Neo4jSchemaRetriever", "retrieve_schema"]


def retrieve_schema(
    question: str,
    mode: str = "neo4j",
    *,
    db_path: str | Path | None = None,
    top_k: int = 5,
) -> str:
    """Retrieve flat schema or the explicitly labeled offline Neo4j fallback."""
    if mode == "flat":
        retriever: SchemaRetriever = FlatSchemaRetriever(db_path)
    elif mode == "neo4j":
        retriever = Neo4jSchemaRetriever(db_path)
    else:
        raise ValueError(f"Unknown schema mode {mode!r}; choose 'flat' or 'neo4j'.")
    return retriever.retrieve(question, top_k)
