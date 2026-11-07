"""Controlled flat-versus-graph Spider retrieval experiment.

Gold SQL and annotations stay in this evaluation module. The retrievers receive
only a question; generation receives only the question and retrieved context.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from src.agents import generate_sql
from src.db import execute_sql
from src.llm import MockProvider, SQLProvider
from src.schema.build_graph import build_schema_graph
from src.schema.flat_retriever import FlatSchemaRetriever
from src.schema.neo4j_retriever import Neo4jSchemaRetriever
from src.schema.neo4j_store import open_driver_from_env, upload_schema_graph
from src.schema.spider_cases import file_sha256, validate_cases
from src.schema.spider_metrics import count_context_tokens, retrieval_metrics, summarize_arm
from src.score import results_equal
from src.verifiers import check_syntax


def _database_path(root: Path, db_id: str) -> Path:
    if not db_id or Path(db_id).name != db_id or db_id in {".", ".."}:
        raise ValueError("Invalid Spider database ID")
    path = root / "database" / db_id / f"{db_id}.sqlite"
    if not path.is_file():
        raise FileNotFoundError(f"Spider SQLite database is missing: {db_id}")
    return path


def _generate_and_score(
    question: str,
    context: str,
    provider: SQLProvider,
    db_path: Path,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Execute independently generated SQL; expected results are evaluator-only."""
    outcome: dict[str, Any] = {
        "sql_generated": False, "sql": "", "syntax_ok": False,
        "execution_ok": False, "result_correct": False,
        "rows": [], "columns": [], "generation_time_ms": None,
        "execution_time_ms": None, "error": "",
    }
    try:
        started = perf_counter()
        sql = generate_sql(question, context, provider=provider)
        outcome["generation_time_ms"] = (perf_counter() - started) * 1000
        outcome["sql"] = sql
        outcome["sql_generated"] = bool(sql.strip())
        syntax = check_syntax(sql, db_path=db_path)
        outcome["syntax_ok"] = bool(syntax["ok"])
        if not syntax["ok"]:
            outcome["error"] = syntax.get("error") or "Syntax/safety verification failed."
            return outcome
        actual = execute_sql(sql, db_path=db_path)
        outcome.update(
            execution_ok=True, rows=actual["rows"], columns=actual["columns"],
            execution_time_ms=actual["execution_time_ms"],
        )
        # SQL aliases are not semantic mismatches. Preserve column positions,
        # count, row multiplicity, and values through the shared scorer.
        outcome["result_correct"] = results_equal(
            actual["rows"], [str(index) for index in range(len(actual["columns"]))],
            expected["rows"], [str(index) for index in range(len(expected["columns"]))],
        )
    except Exception as exc:
        # Provider adapters must redact credential material from their errors.
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    return outcome


def run_schema_experiment(
    dataset_root: str | Path,
    case_manifest: dict[str, Any],
    *,
    backend: str = "local_graph",
    top_k: int = 5,
    repetitions: int = 1,
    provider: SQLProvider | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    temperature: float = 0,
    driver: Any = None,
    neo4j_database: str | None = None,
    tokenizer: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    """Compare exactly the retrieved schema while holding all other nodes fixed.

    ``local_graph`` is an offline diagnostic, never Neo4j evidence. ``neo4j``
    uploads each selected schema once before timing and requires actual Neo4j
    retrieval with no fallback. A supplied driver remains caller-owned. SQL
    generation is opt-in through a real provider; no-provider reports leave
    execution and answer accuracy unavailable.
    """
    if backend not in {"local_graph", "neo4j"}:
        raise ValueError("backend must be 'local_graph' or 'neo4j'")
    if top_k < 1 or repetitions < 1:
        raise ValueError("top_k and repetitions must be positive")
    if provider is not None and (isinstance(provider, MockProvider) or getattr(provider, "is_mock", False) or getattr(provider, "is_oracle", False)):
        raise ValueError("Mock/oracle providers cannot establish schema experiment execution accuracy")
    if provider is not None and getattr(provider, "temperature", temperature) != temperature:
        raise ValueError("Provider temperature does not match the experiment control")
    if provider is not None and model is not None and getattr(provider, "model", model) != model:
        raise ValueError("Provider model does not match the experiment control")
    root = Path(dataset_root)
    validate_cases(case_manifest, root)
    cases = case_manifest["cases"]
    paths = {case["db_id"]: _database_path(root, case["db_id"]) for case in cases}
    owned_driver = backend == "neo4j" and driver is None
    if owned_driver:
        driver = open_driver_from_env()
    setup: list[dict[str, Any]] = []
    retrievers: dict[str, dict[str, Any]] = {}
    measured: list[dict[str, Any]] = []
    try:
        for db_id, path in paths.items():
            started = perf_counter()
            payload = build_schema_graph(path, database_id=db_id)
            uploaded = upload_schema_graph(payload, driver=driver, database=neo4j_database) if backend == "neo4j" else None
            setup.append({
                "db_id": db_id, "schema_id": payload["schema_id"],
                "sqlite_sha256": file_sha256(path), "upload": uploaded,
                "setup_latency_ms": (perf_counter() - started) * 1000,
                "included_in_retrieval_timing": False,
            })
            retrievers[db_id] = {
                "flat": FlatSchemaRetriever(path),
                "graph": Neo4jSchemaRetriever(path, driver=driver, database=neo4j_database, strict=True, backend=backend),
            }

        for case_index, case in enumerate(cases):
            question, db_id = case["question"], case["db_id"]
            samples: dict[str, list[dict[str, Any]]] = {"flat": [], "graph": []}
            orders: list[list[str]] = []
            for repetition in range(repetitions):
                order = ["flat", "graph"] if (case_index + repetition) % 2 == 0 else ["graph", "flat"]
                orders.append(order)
                for arm in order:
                    started = perf_counter()
                    result = retrievers[db_id][arm].retrieve_with_metadata(question, top_k=top_k)
                    elapsed = (perf_counter() - started) * 1000
                    expected_backend = "flat" if arm == "flat" else backend
                    if result.backend != expected_backend:
                        raise RuntimeError(f"Expected {expected_backend} retrieval; got {result.backend}. Fallback results are excluded.")
                    samples[arm].append({
                        "context": result.context, "tables": list(result.tables),
                        "columns": list(result.columns), "relationships": list(result.relationships),
                        "backend": result.backend, "schema_id": result.schema_id,
                        "latency_ms": elapsed, "instrumented_latency_ms": result.latency_ms,
                    })
            arms: dict[str, dict[str, Any]] = {}
            for arm in ("flat", "graph"):
                representative = samples[arm][0]
                arms[arm] = {
                    **{key: representative[key] for key in ("context", "tables", "columns", "relationships", "backend", "schema_id")},
                    "context_tokens": count_context_tokens(representative["context"], tokenizer),
                    "context_characters": len(representative["context"]),
                    "retrieval_latencies_ms": [sample["latency_ms"] for sample in samples[arm]],
                    "instrumented_latencies_ms": [sample["instrumented_latency_ms"] for sample in samples[arm]],
                    "retrieval_samples": samples[arm],
                    "metadata_stable_across_repetitions": all(
                        all(sample[key] == representative[key] for key in ("context", "tables", "columns", "relationships"))
                        for sample in samples[arm]
                    ),
                    "retrieval_metrics": retrieval_metrics(
                        case["required_tables"], case["required_columns"], case["required_joins"],
                        representative["tables"], representative["columns"], representative["relationships"],
                    ),
                    "generation": None,
                }
            if provider is not None:
                # Reference query is executed separately and never crosses the
                # generation/retrieval boundary. Failure aborts an invalid eval.
                expected = execute_sql(case["reference_sql"], db_path=paths[db_id])
                for arm in orders[0]:
                    arms[arm]["generation"] = _generate_and_score(question, arms[arm]["context"], provider, paths[db_id], expected)
            measured.append({
                "id": case["id"], "db_id": db_id, "question": question,
                "source_index": case["source_index"],
                "gold": {key: case[key] for key in ("required_tables", "required_columns", "required_joins", "reference_sql")},
                "retrieval_orders": orders, "generation_order": orders[0] if provider else [],
                "arms": arms,
            })
    finally:
        if owned_driver:
            driver.close()

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": backend, "diagnostic": backend == "local_graph",
        "live_neo4j_measured": backend == "neo4j",
        "generation_enabled": provider is not None,
        "provider": provider_name or (type(provider).__module__ + ":" + type(provider).__qualname__ if provider else None),
        "model": model or getattr(provider, "model", None),
        "request_model": getattr(provider, "api_model", model or getattr(provider, "model", None)),
        "temperature": temperature,
        "top_k": top_k, "retrieval_repetitions": repetitions,
        "controls": {
            "same_questions": True, "same_database_per_case": True,
            "same_provider_instance": True, "same_model_and_temperature": True,
            "generator": "src.agents.generate_sql", "syntax_verifier": "src.verifiers.check_syntax",
            "executor": "src.db.execute_sql", "scorer": "src.score.results_equal",
            "schema_context_is_only_changed_generation_input": True,
            "gold_passed_to_retriever_or_generator": False,
            "optimizer_semantic_result_verifier": "excluded from both arms to isolate retrieval",
            "timing_scope": "wall time of retrieve_with_metadata; setup/upload and generation excluded",
            "order": "AB/BA alternates by case and repetition; generation follows first retrieval order",
            "comparison": "unordered rows with duplicates; positional columns ignore alias names",
        },
        "limitations": [
            "Ten gold-selected cases are a small controlled sample, not the official Spider benchmark.",
            "Flat full-schema recall is expected to be 100%; precision/context size measure selectivity separately.",
            "Local graph diagnostics do not establish Neo4j service latency or live end-to-end gains.",
            "Retrieval-only reports have no SQL execution or result-accuracy measurement.",
            "Unordered result comparison does not verify requested row ordering or answer prose.",
            "Model generation can vary even at temperature zero; no causal claim from one run.",
        ],
    }
    return {
        "manifest": manifest, "case_manifest": case_manifest,
        "graph_setup": setup, "cases": measured,
        "summary": {arm: summarize_arm(measured, arm) for arm in ("flat", "graph")},
    }


def _format_metric(value: Any, *, percent: bool = False, unavailable: str = "N/A") -> str:
    if value is None:
        return unavailable
    if percent:
        return f"{value:.1%}"
    return f"{value:.2f}" if isinstance(value, (int, float)) else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    """Render paired metric results with explicit diagnostic/measurement scope."""
    manifest = report["manifest"]
    graph_title = "Neo4j (live)" if manifest["backend"] == "neo4j" else "Local graph (offline diagnostic)"
    lines = [
        "# Spider schema retrieval experiment", "",
        f"Backend: **{graph_title}**. Cases: {len(report['cases'])}. "
        f"Generation: {'enabled' if manifest['generation_enabled'] else 'disabled; execution/result accuracy are TBD'}.", "",
        "| Metric | Flat schema | " + graph_title + " |",
        "|---|---:|---:|",
    ]
    metric_rows = (
        ("Required table recall", "table_recall", True),
        ("Table precision", "table_precision", True),
        ("Exact table set", "exact_table_set_rate", True),
        ("Required column recall", "column_recall", True),
        ("Column precision", "column_precision", True),
        ("Required FK-edge recall", "join_recall", True),
        ("FK-edge precision", "join_precision", True),
        ("Complete required join path", "join_path_coverage", True),
        ("Mean context tokens/estimate", "mean_context_tokens", False),
        ("Mean retrieval latency (ms)", "mean_retrieval_latency_ms", False),
        ("Median retrieval latency (ms)", "median_retrieval_latency_ms", False),
        ("SQL generation success", "sql_generation_success_rate", True),
        ("Syntax/safety success", "syntax_success_rate", True),
        ("Execution success", "execution_success_rate", True),
        ("Result accuracy", "result_accuracy", True),
        ("Mean successful execution latency (ms)", "mean_execution_time_ms", False),
    )
    for title, key, percent in metric_rows:
        flat, graph = (report["summary"][arm][key] for arm in ("flat", "graph"))
        unavailable = "N/A (no successful executions)" if manifest["generation_enabled"] else "TBD (generation disabled)"
        lines.append(f"| {title} | {_format_metric(flat, percent=percent, unavailable=unavailable)} | {_format_metric(graph, percent=percent, unavailable=unavailable)} |")
    lines.extend(("", "Token method: `" + report["summary"]["flat"]["context_token_method"] + "`.", "", "## Per-case retrieval", "", "| Case (zero-based source index) | Database | Required tables | Flat table recall | Graph table recall | Graph complete join path |", "|---|---|---:|---:|---:|---:|"))
    for case in report["cases"]:
        flat, graph = (case["arms"][arm]["retrieval_metrics"] for arm in ("flat", "graph"))
        lines.append(f"| {case['id']} ({case['source_index']}) | {case['db_id']} | {len(case['gold']['required_tables'])} | {flat['tables']['recall']:.0%} | {graph['tables']['recall']:.0%} | {'yes' if graph['join_path_covered'] else 'no'} |")
    lines.extend(("", "## Controls and limits", ""))
    lines.extend("- " + limit for limit in manifest["limitations"])
    lines.extend(("", "The JSON sibling contains source hashes, fixed controls, all retrieved contexts, qualified tables/columns/FK edges, timing samples, and generated SQL/results when enabled.", ""))
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: str | Path) -> tuple[Path, Path]:
    """Write a JSON artifact and Markdown sibling; return both paths."""
    path = Path(output)
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    markdown = path.with_suffix(".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    return path, markdown
