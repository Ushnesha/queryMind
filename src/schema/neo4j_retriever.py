"""Explicit offline fallback for the future internal Neo4j retriever."""

from pathlib import Path

from src.schema.flat_retriever import FlatSchemaRetriever


class Neo4jSchemaRetriever:
    """Keep the graph interface runnable before a Neo4j integration is supplied."""

    fallback_reason = "Neo4j retrieval is a starter placeholder; using flat SQLite schema."

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._fallback = FlatSchemaRetriever(db_path)

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Return a clearly labeled flat fallback; never contact a Neo4j server."""
        # TODO(feature/schema-graph): replace with real internal graph retrieval.
        return f"-- {self.fallback_reason}\n{self._fallback.retrieve(question, top_k)}"
