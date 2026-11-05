"""Schema retrieval protocol shared by flat and future graph implementations."""

from typing import Protocol


class SchemaRetriever(Protocol):
    """Retrieve a textual schema context without coupling callers to storage."""

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Return schema context for a question; top_k must be positive."""
        ...
