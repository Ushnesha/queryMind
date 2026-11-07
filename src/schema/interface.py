"""Stable retrieval protocol and optional, JSON-safe retrieval instrumentation."""

from dataclasses import asdict, dataclass, field
import re
from typing import Any
from typing import Protocol


class SchemaRetriever(Protocol):
    """Retrieve a textual schema context without coupling callers to storage."""

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Return schema context for a question; top_k must be positive."""
        ...


@dataclass(frozen=True)
class RetrievalResult:
    """Instrumented context; backend distinguishes real Neo4j from diagnostics.

    ``retrieve`` remains the string interface. ``retrieve_with_metadata`` exposes
    this record for experiments without putting a driver in shared AgentState.
    Relationships describe column-level foreign keys, not inferred SQL joins.
    """

    context: str
    tables: list[str]
    columns: list[str]
    relationships: list[dict[str, Any]]
    backend: str
    latency_ms: float
    schema_id: str
    seed_tables: list[str] = field(default_factory=list)
    fallback_reason: str = ""

    @property
    def metrics(self) -> dict[str, Any]:
        """Return serializable retrieval metrics; token estimate is not billing usage."""
        return {
            "backend": self.backend,
            "tables_returned": list(self.tables),
            "column_count": len(self.columns),
            "relationship_count": len(self.relationships),
            "context_characters": len(self.context),
            "schema_tokens": len(re.findall(r"\w+|[^\w\s]", self.context)),
            "token_count_method": "lexical_estimate",
            "latency_ms": self.latency_ms,
            "schema_id": self.schema_id,
            "fallback_reason": self.fallback_reason,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert the complete retrieval record to plain JSON-compatible data."""
        return asdict(self)
