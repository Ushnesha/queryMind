# QueryMind

**A Self-Correcting Agentic Text-to-SQL Assistant with Query Optimization**

Academic capstone repository. The five Milestone 2 components are integrated
into one runnable Text-to-SQL pipeline, with offline tests and preliminary evaluation.

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

Current integrated behavior:

- All five feature implementations are merged into `main`: orchestration,
  schema retrieval, verification, optimization, and evaluation/Streamlit.
- SQL generation and bounded repair use the shared mock or OpenAI-compatible
  provider. Safety, SQLite compilation, deterministic semantic checks, result
  sanity checks, and optional model judges run through the same pipeline.
- Neo4j retrieval uses a schema generated from SQLite and records table, join,
  size, latency, and backend metadata. An unavailable graph produces an explicit
  flat-schema fallback.
- Optimizer candidates must pass read-only validation, result equality, and a
  query-plan improvement gate. Mock mode never calls a model for rewrites.
- The evaluation harness supports b1, b2-small (three-sample result voting),
  QueryMind, node ablations, schema comparisons, and JSON/JSONL replay.
- The offline mock supports customer-count and top-N customer-spending questions.
  Use a live provider for broader natural-language coverage. Unsupported mock
  questions are generic refusals, not evidence that missing fields were detected.

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

Base dependencies are pinned in `requirements.txt`; Neo4j support is optional:

```bash
.venv/bin/python -m pip install -r requirements-schema.txt
```

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

### Running QueryMind

```bash
make demo
SQLITE_DB=data/analytics.db python -m src.run --question "Who are the top 3 customers by total spending?" --schema-mode flat
SQLITE_DB=data/analytics.db python -m src.run --question "How many customers are there?" --schema-mode neo4j
```

CLI JSON includes the answer, rows, columns, SQL history, assumptions, verification
flags, warnings, trace, and timing. `status=success` means execution completed;
verification flags report the completed enabled checks. Deterministic semantic
checks cover specific cues and missing concepts; they do not prove arbitrary SQL correctness.
`status=refused` includes unsupported mock questions and exhausted repairs;
`status=error` indicates a runtime failure. The CLI exits 1 for errors and 0 for
completed/refused runs. Optional `--trace PATH` appends a complete JSONL record.

### Running Streamlit

```bash
make seed
make ui
# Equivalent after activation:
SQLITE_DB=data/analytics.db streamlit run app.py
```

The UI displays the answer, table, SQL, assumptions, missing fields, verification
status/warnings, and expandable trace. It uses only the public orchestrator API.

### Integrated experiments

```bash
make eval          # Paired b1/b2-small/QueryMind plus full 17-case b1/QueryMind
make ablation      # Ten cases across six configurations
make schema-graph  # Inspect the demo SQLite schema without uploading
make benchmark     # 30 Spider optimizer cases; requires data/spider_data
.venv/bin/python -m scripts.run_eval --schema-comparison --db-path data/analytics.db --output eval/results/integrated/schema.json --markdown eval/results/integrated/schema.md
```

Fresh reports go into ignored `eval/results/integrated/`; historical branch
reports remain intact. Mock accuracy measures its two supported templates,
not live-model quality. See [INTEGRATION.md](docs/INTEGRATION.md) for validation.

### Model and graph configuration

Keep credentials in `.env`. Set `model.provider: openai` (or `opencode`) in
`config/settings.yaml` to enable the existing live provider. Configure its
base URL, API key, and model using the environment names in `.env.example`.
The optimizer and both judges use that same provider. The default remains `mock`.

The UI loads `.env` and uses `schema.default_mode` from the settings file.
`make ui` explicitly selects `data/analytics.db` because the mock and milestone
fixture use customers/orders. This also avoids an existing `.env` database
selection silently redirecting the demo to a Spider schema. For a different
prepared database, use `make ui DEMO_DB=path/to/database.sqlite` with a live model.
The seeder preserves any existing database.

For actual Neo4j retrieval, configure `NEO4J_URI`, `NEO4J_USER`, and
`NEO4J_PASSWORD`, start the local service if needed, and upload the demo schema:

```bash
docker compose -f compose.neo4j.yaml up -d
.venv/bin/python -m scripts.build_schema_graph --db data/analytics.db --upload
make ui
```

The trace distinguishes graph retrieval from flat fallback. For direct CLI runs
with another database, pass `--db-path`; this takes precedence over `.env`.

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
