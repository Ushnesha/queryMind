# Shared component contracts

Python 3.11 compatible. Import public interfaces shown below. All defaults are
offline. Run `make seed` before examples that use the configured database. Tests
instead inject a temporary database path or replacement `Components` instance.

## AgentState

`from src.state import AgentState`

The `TypedDict(total=False)` is the primary contract. The orchestrator initializes
all starter fields. Values are JSON-compatible data; connections, SDK clients,
graph objects, and providers stay outside state.

| Group | Fields |
|---|---|
| Input/schema | `question: str`, `schema_mode: str`, `schema_context: str` |
| Generation | `sql: str`, `sql_history: list[str]` |
| Syntax/safety | `syntax_ok: bool`, `syntax_error: str`, `safety_ok: bool` |
| Semantics | `semantic_ok: bool`, `semantic_reason: str`, `answerable: bool`, `missing_fields: list[str]`, `assumptions: list[str]` |
| Optimization | `original_sql: str`, `optimized_sql: str`, `optimization_applied: bool`, `original_plan: list[Any]`, `optimized_plan: list[Any]` |
| Execution | `rows: list[Any]`, `columns: list[str]` |
| Result | `result_ok: bool`, `result_warnings: list[str]` |
| Response | `final_answer: str` |
| Control | `repair_count: int`, `optimizer_count: int`, `status: Literal['success', 'refused', 'error']`, `error: str` |
| Observability | `trace: list[dict[str, Any]]`, `metrics: dict[str, Any]` |

`semantic_ok` and `result_ok` stay false for placeholder or disabled nodes. Consult
trace status to distinguish unrun/disabled/placeholder from failed. A successful
execution is not proof of semantic correctness. `sql_history` includes every
generation attempt and accepted optimizer candidate. `original_sql` is the verified
pre-optimization statement; `sql` and `optimized_sql` contain the final statement
after the optimization stage, even when unchanged.

## Schema retrieval

```python
from src.schema import SchemaRetriever, FlatSchemaRetriever, Neo4jSchemaRetriever, retrieve_schema

context: str = retrieve_schema("How many customers are there?", mode="flat")
retriever: SchemaRetriever = FlatSchemaRetriever()
context = retriever.retrieve("How many customers are there?", top_k=5)
```

Signatures:

```python
retrieve_schema(question: str, mode: str = "neo4j", *, db_path=None, top_k: int = 5) -> str
SchemaRetriever.retrieve(question: str, top_k: int = 5) -> str
FlatSchemaRetriever(db_path=None)
Neo4jSchemaRetriever(db_path=None, *, driver=None, database=None, strict=False, backend="neo4j")
```

Retrieval returns a schema string containing tables, columns/types, primary keys,
foreign keys, and indexes. `mode` must be `flat` or `neo4j`. Flat retrieval returns
the complete schema. Neo4j retrieval ranks identifiers from the question, takes
up to `top_k` seed tables, and includes intermediate tables from native Neo4j
shortest paths. Path expansion may exceed `top_k`; every selected table retains
all its columns. Both modes use the same text formatter.

Both retrievers additionally expose `retrieve_with_metadata(question, top_k=5)`
returning `RetrievalResult(context, tables, columns, relationships, backend,
latency_ms, schema_id, seed_tables, fallback_reason)`. `columns` are qualified
names; relationships identify column-level FKs. `.metrics` and `.to_dict()` return
JSON-compatible instrumentation. Default token counts are labeled lexical
estimates, not the configured model's tokenizer.

The live backend loads versioned graph metadata and calls Neo4j's `shortestPath`
over `HAS_COLUMN|REFERENCES`, bounded at 32 relationships. It preserves bridge
tables even where a path passes through their columns. `strict=True` refuses
missing credentials, unavailable graphs, or service failures instead of silently
substituting flat schema. The default non-strict path preserves the original
starter fallback prefix and reports `backend='flat_fallback'` when unconfigured.
Unknown questions with no identifier matches return the full available schema
with an explicit reason. `backend='local_graph'` selects a Python BFS diagnostic;
it is never reported as live Neo4j evidence.

`build_schema_graph(db_path, *, database_id=None)` in `src.schema.build_graph`
uses read-only SQLite metadata PRAGMAs and returns a JSON payload including
tables/columns/indexes, composite FK edges, database ID, schema fingerprint, and
schema ID. `src.schema.neo4j_store.upload_schema_graph(payload, *, driver,
database=None)` idempotently uploads the requested Table/Column/Index graph plus
version metadata using parameterized `MERGE`. It preserves existing versions and
unrelated graph data. `load_schema_graph` reads a version back; `expand_join_paths`
performs native graph path expansion. Callers own supplied drivers. The optional
SDK is installed from `requirements-schema.txt`; imports and ordinary tests make
no service calls. Only explicit CLI entry points load `.env`.

The controlled ten-question Spider experiment lives under `src/schema/` to avoid
changing Developer 5's evaluation code. See
[SCHEMA_EXPERIMENT.md](SCHEMA_EXPERIMENT.md) for controls, metrics, local Neo4j
setup, and measured diagnostic/live results. The completed ten-question ASU run
scored 6/10 correct results in both arms, with about half the estimated schema
context for Neo4j and higher retrieval latency. Its full evidence and caveats are
recorded in that document.

## SQL generation and provider

```python
from src.agents import generate_sql
sql = generate_sql("How many customers are there?", context)
# SELECT COUNT(*) AS customer_count FROM customers
```

```python
generate_sql(question: str, schema_context: str, *, provider=None, feedback: str | None = None) -> str
```

`src.llm.SQLProvider` is a protocol with
`generate(question: str, schema_context: str) -> str`. `get_provider('mock')` returns
`MockProvider`; unsupported provider names raise `ValueError`. The wrapper appends
optional repair feedback to schema context. SQL output remains untrusted until
safety/syntax checks. Unsupported mock questions raise `ValueError`; orchestration
turns this into a refusal. The starter supports only its documented customer count
and top-N templates. No model API is implemented or called.

## Syntax and mandatory safety

```python
from src.verifiers import check_safety, check_syntax
check_safety("SELECT COUNT(*) FROM customers")
# {"ok": True, "error": None}
check_syntax("SELECT COUNT(*) FROM customers")
# {"ok": True, "error": None}
```

```python
check_safety(sql: str) -> dict  # keys: ok: bool, error: str | None
check_syntax(sql: str, *, db_path=None) -> dict  # same keys
```

Safety delegates to the shared lexical SELECT/WITH guard. Syntax additionally
compiles with SQLite `EXPLAIN` on a protected connection; it checks references as
well as syntax. The safety layer rejects multiple statements, mutation keywords,
external/file functions, and user PRAGMAs. A connection-level authorizer, `mode=ro`
and `query_only` independently enforce read-only execution. Introspection alone
uses permitted metadata PRAGMAs. The guard is conservative and is not a full SQL
parser. Disabling syntax analysis does not disable safety or executor enforcement.

## Semantic verification

```python
from src.verifiers import verify_semantics
decision = verify_semantics("How many customers are there?", sql, context)
# {
#   "matches_question": True, "answerable": True,
#   "missing_fields": [], "assumptions": ["...alignment has not been verified."],
#   "reason": "Starter input checks passed; semantic alignment is unverified.",
#   "status": "placeholder",
# }
```

```python
verify_semantics(question: str, sql: str, schema_context: str) -> dict
```

Required result keys: `matches_question: bool`, `answerable: bool`,
`missing_fields: list[str]`, `assumptions: list[str]`, `reason: str`.
The starter adds `status='placeholder'`; its positive booleans mean nonempty input
structure only. The orchestrator continues but leaves `semantic_ok=False`. A future
implementation can omit the placeholder status or use an honest validated status.
False answerability or question alignment causes a refusal before execution.

## Optimization

```python
from src.optimizer import optimize_sql
candidate = optimize_sql(sql, "How many customers are there?", context)
# {"changed": False, "sql": sql, "reason": "...kept SQL unchanged.",
#  "plan_before": [[...]], "plan_after": [[...]]}
```

```python
optimize_sql(sql: str, question: str, schema_context: str, *, db_path=None) -> dict
```

Keys: `changed: bool`, `sql: str`, `reason: str`, `plan_before: list`,
`plan_after: list`. The starter returns unchanged SQL and actual local plan data
where available. Plan errors preserve SQL and appear in the reason. There is no
claim of improved performance. `src.optimizer.explain_query_plan(sql, *, db_path=None)`
returns JSON-safe plan rows. `compare_results(rows_before, columns_before,
rows_after, columns_after)` delegates to the shared scorer.

**Optimizer contract:** future implementations must enforce result equivalence
before returning `changed=True`, account for ordered results where relevant, and
return a safe candidate. The orchestrator reruns safety on each changed candidate;
the executor still independently rejects unsafe SQL. It calls the optimizer at
most twice and stops immediately on `changed=False`.

## SQLite execution and shared baseline helpers

```python
from src.db import execute_sql
result = execute_sql("SELECT COUNT(*) AS customer_count FROM customers")
# {"rows": [[4]], "columns": ["customer_count"], "execution_time_ms": ...}
```

```python
execute_sql(sql: str, *, db_path=None) -> dict
connect_readonly(db_path=None) -> sqlite3.Connection
introspect_schema(db_path=None) -> str
validate_readonly(sql: str) -> str
```

Execution returns `rows: list[list[Any]]`, `columns: list[str]`,
`execution_time_ms: float`. Connections are opened against an existing database
only; missing files raise `FileNotFoundError` with seed instructions. Invalid SQL
raises `ValueError` or a SQLite exception. Callers of `connect_readonly` own closing
the connection; use `contextlib.closing`. Ordinary `with connection` manages
transactions but does not close a SQLite connection.

SQLite TEXT/INTEGER/finite REAL/NULL map to normal JSON scalar values. To preserve
types and strict JSON, BLOB cells use `{"type":"blob","hex":"0061"}` and nonfinite
floats use `{"type":"nonfinite_float","value":"inf"}` (or `-inf`/`nan`). The
executor currently fetches complete results; paging, timeouts, and resource limits
belong to later execution work.

`src.score.normalize_result(rows, columns)` returns canonical columns and sorted
JSON row strings. `results_equal(rows_before, columns_before, rows_after,
columns_after) -> bool` compares exact column labels and unordered row multisets,
preserving duplicate counts and JSON types. It does not apply numeric tolerance
or validate row order. `src.baseline.run_baseline(question, *, db_path=None)` reuses
the same schema, mock provider and executor, returning question, SQL and result.
It is a new starter baseline, not a recovered stakeholder implementation.

## Result verification

```python
from src.verifiers import verify_result
verification = verify_result("How many customers are there?", sql, result["rows"], result["columns"])
# {"ok": True, "warnings": ["Starter result verification checks table shape only."],
#  "statistics": {"row_count": 1, "column_count": 1}, "status": "placeholder"}
```

```python
verify_result(question: str, sql: str, rows: list, columns: list[str]) -> dict
```

Required keys: `ok: bool`, `warnings: list[str]`, `statistics: dict`.
The starter checks row widths, warns about empty results/duplicate columns, and
adds `status='placeholder'`. This leaves state `result_ok=False` even if structural
checks pass. Malformed row widths produce `status='error'` in the run. A future
verifier can replace the placeholder with question-aware result sanity checks.

## Response generation

```python
from src.agents import generate_response
answer = generate_response({"answerable": True, "rows": [[4]], "columns": ["customer_count"]})
# The query returned customer_count = 4. See verification details.
```

```python
generate_response(state: AgentState) -> str
```

The deterministic starter formats scalar results, row counts, empty results,
refusals/missing fields, and execution errors. Grounded natural-language synthesis
is deferred. Response generation runs on success, refusal, and error paths.

## Orchestrator and dependency injection

```python
from src.orchestrator import run_querymind
state = run_querymind(
    "Who are the top 3 customers by total spending?",
    schema_mode="flat",
    enable_syntax=True,
    enable_semantic=True,
    enable_optimizer=True,
    enable_result_verifier=True,
)
```

```python
run_querymind(
    question: str,
    schema_mode: str | None = None,
    enable_syntax: bool = True,
    enable_semantic: bool = True,
    enable_optimizer: bool = True,
    enable_result_verifier: bool = True,
    *, db_path=None, provider=None, settings=None, components=None,
) -> AgentState
```

`schema_mode=None` uses YAML's `neo4j` default with the explicit local fallback.
The CLI and UI explicitly choose `flat`. `provider` implements `SQLProvider`;
`settings` is a `src.config.Settings` dataclass instance. `Components` is a frozen
dataclass of node callables. Replace a single node with
`dataclasses.replace(Components(), verify_semantics=my_verifier)`; maintain its
public arguments and returned keys. Database-aware callables must accept `db_path`;
the generator must accept `provider` and `feedback` keyword arguments.
Tests demonstrate replacing all database nodes to run without any SQLite file.

Repair count is the number of extra generations, so a budget of three permits
four total generation attempts. Node failures become error states; invalid mock
questions and verification exhaustion become refusals. Neither importing modules
nor running a query writes databases, trace files, or credentials. A CLI caller
may explicitly persist a trace.

## Trace and configuration

```python
from src.trace import add_trace, write_jsonl
add_trace(state, "semantic_verifier", "placeholder", 0.1, "Starter input checks only.")
write_jsonl("logs/run.jsonl", state)
```

Every event has `node`, `status`, `latency_ms`, `reason`. Statuses include `pass`,
`fail`, `error`, `placeholder`, `skipped`, and `retry`. Each complete state is one
strict JSONL record. Metrics include `total_latency_ms`, and on execution,
`execution_time_ms`; result checks add `result_statistics`.

`src.config.load_settings(path=None) -> Settings` reads YAML safely. Database and
trace paths resolve relative to the repository. `SQLITE_DB` overrides the database
path; credentials never enter settings YAML. Model temperature/provider, schema
mode/top_k, and bounded repair/optimizer budgets are exposed as typed sections.

## Evaluation contracts

Public imports come from `src.evaluation`:

- `load_questions(path) -> list[dict]`: YAML mapping with a `questions` list;
  each item has `id`, `question`, optional reference `sql`.
- `run_evaluation(questions, *, db_path=None, run_options=None) -> dict`:
  `scope`, `cases` (`id`, `question`, `correct: bool | None`, `state`) and `metrics`.
  Compares outputs with read-only reference SQL using the shared scorer.
- `summarize_runs(states) -> dict`: run/success/refusal/error counts, success rate,
  total rows, mean total latency and mean execution latency. Empty rate is 0.0;
  absent timings produce `None` means. Timings average recorded values only.
- `summarize_results(cases) -> dict`: case/scored/correct counts and result
  accuracy. Only boolean `correct` values enter the denominator; no scored cases
  gives `result_accuracy=0.0`.
- `ablation_variants() -> dict`: all enabled plus one configuration disabling
  each optional node. `run_ablation(question, *, db_path=None) -> dict` exercises
  these on one question and clearly labels the output as a smoke test.
- `src.evaluation.b2.run_self_consistency(...) -> dict`: explicit
  `implemented=False` placeholder; no experiment is run.

These are integration tools for the two demo fixtures, not completed evaluation,
self-consistency or ablation experiments. Reference accuracy does not measure
plain-English answer quality or prove semantic verifier quality.
