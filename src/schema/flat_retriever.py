"""Complete flat SQLite schema, rendered identically to selected graph contexts."""

from pathlib import Path
from time import perf_counter

from src.schema.build_graph import build_schema_graph
from src.schema.context import retrieval_result
from src.schema.interface import RetrievalResult


class FlatSchemaRetriever:
    """Return all tables, columns, foreign keys and indexes as the control arm."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path
        self.last_result: RetrievalResult | None = None

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Return full schema; top_k is validated but never truncates the control."""
        return self.retrieve_with_metadata(question, top_k).context

    def retrieve_with_metadata(self, question: str, top_k: int = 5) -> RetrievalResult:
        """Return the full context and measured retrieval metadata without network."""
        self.last_result = None
        started = perf_counter()
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        payload = build_schema_graph(self.db_path)
        self.last_result = retrieval_result(
            payload, [table["name"] for table in payload["tables"]], backend="flat", started=started,
        )
        return self.last_result
