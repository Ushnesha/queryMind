"""Offline schema retrieval through the existing SQLite introspection boundary."""

from pathlib import Path

from src.db import introspect_schema


class FlatSchemaRetriever:
    """Return the complete flat schema until relevance ranking is implemented."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Introspect SQLite without network; top_k is reserved for later ranking."""
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        # TODO(feature/schema-graph): add question-aware schema ranking.
        return introspect_schema(self.db_path)
