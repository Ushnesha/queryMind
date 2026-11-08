"""Stable public schema interfaces used by the orchestration layer."""

from pathlib import Path

from src.schema.flat_retriever import FlatSchemaRetriever
from src.schema.interface import RetrievalResult, SchemaRetriever
from src.schema.neo4j_retriever import Neo4jSchemaRetriever, Neo4jUnavailableError

__all__ = ["SchemaRetriever", "RetrievalResult", "FlatSchemaRetriever", "Neo4jSchemaRetriever", "Neo4jUnavailableError", "retrieve_schema"]


def retrieve_schema(
    question: str,
    mode: str = "neo4j",
    *,
    db_path: str | Path | None = None,
    top_k: int = 5,
) -> str:
    """Retrieve full flat schema or relevant Neo4j schema with explicit fallback."""
    return retrieve_schema_with_metadata(question, mode, db_path=db_path, top_k=top_k).context


def retrieve_schema_with_metadata(
    question: str, mode: str = "neo4j", *, db_path: str | Path | None = None, top_k: int = 5,
) -> RetrievalResult:
    """Expose retrieval provenance while preserving the public string adapter."""
    if mode == "flat":
        retriever: SchemaRetriever = FlatSchemaRetriever(db_path)
    elif mode == "neo4j":
        retriever = Neo4jSchemaRetriever(db_path)
    else:
        raise ValueError(f"Unknown schema mode {mode!r}; choose 'flat' or 'neo4j'.")
    return retriever.retrieve_with_metadata(question, top_k)
