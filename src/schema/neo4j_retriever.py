"""Question-aware Neo4j retrieval with FK paths and an explicit offline fallback."""

from dataclasses import replace
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from src.schema.build_graph import build_schema_graph
from src.schema.context import retrieval_result
from src.schema.flat_retriever import FlatSchemaRetriever
from src.schema.interface import RetrievalResult
from src.schema.neo4j_store import expand_join_paths, load_schema_graph, open_driver_from_env
from src.schema.relevance import expand_local_join_paths, rank_tables


class Neo4jUnavailableError(RuntimeError):
    """The requested Neo4j retrieval cannot run against a configured graph."""


class Neo4jSchemaRetriever:
    """Rank question/schema identifiers and expand paths through the Neo4j graph.

    ``top_k`` limits seed tables, not intermediate bridge tables. All columns of
    selected tables are retained. No model, gold SQL or benchmark annotations are
    consulted. ``backend='local_graph'`` is an explicitly labeled offline
    diagnostic of the ranking/path algorithm, not a Neo4j measurement.
    """

    # Preserve the starter marker consumed by the existing orchestrator trace.
    fallback_reason = "Neo4j retrieval is a starter placeholder; using flat SQLite schema."

    def __init__(
        self, db_path: str | Path | None = None, *, driver: Any = None,
        database: str | None = None, strict: bool = False, backend: str = "neo4j",
    ) -> None:
        if backend not in {"neo4j", "local_graph"}:
            raise ValueError("backend must be 'neo4j' or 'local_graph'.")
        self.db_path = db_path
        self.driver = driver
        self.database = database or os.environ.get("NEO4J_DATABASE") or None
        self.strict = strict
        self.backend = backend
        self.last_result: RetrievalResult | None = None

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Return relevant schema text, keeping the original public interface."""
        return self.retrieve_with_metadata(question, top_k).context

    def retrieve_with_metadata(self, question: str, top_k: int = 5) -> RetrievalResult:
        """Return context and provenance; strict live mode never uses flat fallback."""
        self.last_result = None
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        started = perf_counter()
        payload = build_schema_graph(self.db_path)
        if not payload["tables"]:
            raise ValueError("The SQLite database has no user tables to retrieve.")
        if self.backend == "local_graph":
            seeds = rank_tables(payload, question, top_k)
            tables = expand_local_join_paths(payload, seeds) if seeds else [t["name"] for t in payload["tables"]]
            self.last_result = retrieval_result(
                payload, tables, backend="local_graph", started=started, seed_tables=seeds,
                fallback_reason="No identifier matches; returned the full schema." if not seeds else "",
            )
            return self.last_result

        configured = all(os.environ.get(name) for name in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"))
        if self.driver is None and not configured:
            return self._fallback(question, top_k, started, "Configure NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD.")
        driver = self.driver
        owns_driver = driver is None
        try:
            if driver is None:
                driver = open_driver_from_env()
            stored = load_schema_graph(driver=driver, schema_id=payload["schema_id"], database=self.database)
            seeds = rank_tables(stored, question, top_k)
            tables = expand_join_paths(driver=driver, schema_id=payload["schema_id"], table_names=seeds,
                                       database=self.database) if seeds else [t["name"] for t in stored["tables"]]
            self.last_result = retrieval_result(
                stored, tables, backend="neo4j", started=started, seed_tables=seeds,
                fallback_reason="No identifier matches; returned the full graph schema." if not seeds else "",
            )
            return self.last_result
        except Exception as exc:
            if self.strict:
                raise Neo4jUnavailableError("Neo4j retrieval failed; check connectivity and upload this schema first.") from exc
            return self._fallback(question, top_k, started, "Neo4j retrieval failed; check connectivity and schema upload.")
        finally:
            if owns_driver and driver is not None:
                driver.close()

    def _fallback(self, question: str, top_k: int, started: float, reason: str) -> RetrievalResult:
        if self.strict:
            raise Neo4jUnavailableError(reason)
        flat = FlatSchemaRetriever(self.db_path).retrieve_with_metadata(question, top_k)
        self.last_result = replace(
            flat, backend="flat_fallback", fallback_reason=reason,
            context=f"-- {self.fallback_reason}\n-- {reason}\n{flat.context}",
            latency_ms=(perf_counter() - started) * 1000,
        )
        return self.last_result
