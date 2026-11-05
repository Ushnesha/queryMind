# QueryMind

**A Self-Correcting Agentic Text-to-SQL Assistant with Query Optimization**

Academic capstone repository. This Milestone 2 foundation gives five developers
stable interfaces and an offline, runnable integration path. It does not implement
the completed research system.

## Repository starting point

The inspected checkout contained only `.git`, with no commits, tracked files,
baseline source, tests, database, evaluation data, or documentation. Consequently,
there was no stakeholder baseline to preserve. The small `src/baseline.py`, mock
provider, scorer, and demo data here are **new starter components**. They share the
same SQLite and provider functions used by the orchestrator. If the stakeholder's
baseline is supplied later, integrate it through these boundaries and preserve its
tests and artifacts.

## Milestone 2 Development

Question → Schema → Generate → Verify → Optimize → Execute → Verify Result → Respond

`src/state.py` contains the shared `AgentState` TypedDict. The Python orchestrator
calls replaceable public node functions and returns a complete JSON-safe state.
Optional node switches support ablation. SQLite execution always enforces its own
read-only guard, even when syntax analysis is disabled. Repair attempts are capped
at three and optimizer calls at two. Imports create no databases or network calls.

Current behavior:

- SQLite schema introspection, guarded execution, syntax compilation, result
  normalization, and JSONL traces work locally.
- SQL generation uses an offline mock for two question templates: “Who are the top
  3 customers by total spending?” (also supports other positive N up to 99) and
  “How many customers are there?”. Other questions produce an explicit refusal.
- `neo4j` mode explicitly falls back to flat SQLite schema. Neo4j is internal
  infrastructure; the interactive input is a natural-language question.
- Semantic and result checks are labeled placeholders. Successful execution does
  not imply that question alignment or answer correctness was verified.
- The optimizer inspects `EXPLAIN QUERY PLAN` and returns unchanged SQL. Graph
  building emits an offline metadata payload. b2 is an explicit unimplemented
  contract; evaluation and ablation commands are small smoke runs.

### Offline setup

Use Python **3.11 or newer**. An initial dependency download is required; subsequent
tests, demos, schema retrieval, and evaluation require neither credentials nor a
Neo4j server.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
make seed
```

If Python 3.11 is managed by `uv` rather than available as `python3.11`, use
`uv venv --python 3.11 .venv` and `uv pip install --python .venv/bin/python -r requirements.txt`
for the environment creation and dependency installation steps. This is the
method used to validate this checkout; its `.venv` is already prepared.

Only pytest, PyYAML, python-dotenv, and Streamlit are direct dependencies. Existing
package pins did not exist; these starter pins were validated on Python 3.11.15.
Neo4j, LangGraph, sqlglot, and a live model SDK are deferred until a feature branch
uses them. Model configuration defaults to `mock`; the example API environment
variables reserve the future provider boundary and are not used by the starter.

`make seed` creates a deterministic fixture with four customers and six orders. It
leaves an existing database untouched. The query path never creates or writes a
database. Set `SQLITE_DB` in the environment to choose a different database. The
starter CLI also reads `.env`; use exported variables for Make targets and the UI.
Configured relative paths resolve against this repository; explicit low-level
database paths are interpreted by SQLite relative to the caller's directory.

### Running tests

```bash
make test
# Equivalent after activation:
pytest
```

Tests create disposable SQLite fixtures, clear model credentials, and block socket
connections. They do not need the generated database in `data/`. Test counts and
the initial environment assessment are recorded in [VALIDATION.md](docs/VALIDATION.md).

### Running baseline

This is the new minimal baseline for the initially empty checkout:

```bash
make baseline-demo
python -m src.baseline --question "How many customers are there?"
make verify-data
```

### Running QueryMind skeleton

```bash
make demo
python -m src.run --question "Who are the top 3 customers by total spending?" --schema-mode flat
python -m src.run --question "How many customers are there?" --schema-mode neo4j
```

CLI JSON includes the answer, rows, columns, SQL history, assumptions, verification
flags, warnings, trace, and timing. `status=success` means execution completed;
placeholder semantic/result checks leave `semantic_ok` and `result_ok` false.
`status=refused` includes unsupported mock questions and exhausted repairs;
`status=error` indicates a runtime failure. The CLI exits 1 for errors and 0 for
completed/refused runs. Optional `--trace PATH` appends a complete JSONL record.

### Running Streamlit

```bash
make seed
make ui
# Equivalent after activation:
streamlit run app.py
```

The UI displays the answer, table, SQL, assumptions, missing fields, verification
status/warnings, and expandable trace. It uses only the public orchestrator API.

### Starter utilities

```bash
make eval          # Two reference-SQL demo cases; also available as make score
make ablation      # Five switch configurations on one demo question
make schema-graph  # Offline graph metadata; does not upload to Neo4j
make benchmark     # Unchanged SQL plans, timings and result equality
```

Generated databases, JSONL logs, and evaluation output are ignored. The deterministic
seeder, two-case YAML fixture, and empty artifact directories are committed source.
Reference comparisons use exact column labels and unordered row multisets, preserve
duplicates and JSON types, and have no numeric tolerance. Ordered answer validation
and rigorous optimization equivalence remain future work.

### Developer branches

| Developer | Branch | Primary ownership |
|---|---|---|
| 1 | `feature/orchestrator` | `src/orchestrator.py`, `src/trace.py`, `tests/test_orchestrator.py`; coordinated state changes |
| 2 | `feature/schema-graph` | `src/schema/`, `tests/test_schema.py`, `scripts/build_schema_graph.py` |
| 3 | `feature/verifiers` | `src/verifiers/`, `tests/test_{syntax,safety,semantic,result}.py` |
| 4 | `feature/optimizer` | `src/optimizer/`, `tests/test_optimizer.py`, `scripts/benchmark_optimizer.py` |
| 5 | `feature/eval-ui` | `src/evaluation/`, `app.py`, `tests/test_metrics.py`, `tests/test_ui.py`, evaluation scripts |

Read [DEVELOPMENT.md](docs/DEVELOPMENT.md) for shared-file coordination, exact branch
commands, and independent handoff checks. [INTERFACES.md](docs/INTERFACES.md) specifies
all public contracts and examples. The integration owner controls shared state,
configuration, dependencies, and baseline adapters.
