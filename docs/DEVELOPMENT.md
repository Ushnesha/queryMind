# Milestone 2 developer handoff

All five feature branches should start from the same committed foundation. This
checkout started without commits; commit the bootstrap first. No branches, commits,
or remote changes are created automatically by the starter.

## Ownership

| Developer | Branch | Files/directories |
|---|---|---|
| 1 | `feature/orchestrator` | `src/orchestrator.py`, `src/trace.py`, `tests/test_orchestrator.py`; technical owner of `src/state.py` with integration-owner review |
| 2 | `feature/schema-graph` | `src/schema/`, `tests/test_schema.py`, `scripts/build_schema_graph.py` |
| 3 | `feature/verifiers` | `src/verifiers/`, `tests/test_syntax.py`, `tests/test_safety.py`, `tests/test_semantic.py`, `tests/test_result.py` |
| 4 | `feature/optimizer` | `src/optimizer/`, `tests/test_optimizer.py`, `scripts/benchmark_optimizer.py` |
| 5 | `feature/eval-ui` | `src/evaluation/`, `app.py`, `tests/test_metrics.py`, `tests/test_ui.py`, `scripts/run_eval.py`, `scripts/run_ablation.py` |

**Integration-owner controlled:** `src/state.py`, `config/settings.yaml`,
`requirements.txt`, `README.md`, `Makefile`. Also coordinate `src/config.py`,
`src/run.py`, `src/agents/`, shared `tests/conftest.py`, `.env.example`, and baseline
adapters `src/db.py`, `src/llm.py`, `src/score.py`, `src/baseline.py`,
`scripts/seed_db.py`, and `eval/questions.yaml`. Developer 1 proposes state changes;
the integration owner coordinates them before other branches depend on them.

Keep feature work in owned modules. Request shared contract changes through a
small integration change and merge it into affected branches before using it.
Do not independently regenerate shared scaffolding or dependency files. Reuse
`src.db`, `src.llm`, and `src.score` rather than creating competing implementations.

## Contracts and next implementation

| Developer | Interface to preserve | Implement next | Independent check |
|---|---|---|---|
| 1 | `run_querymind(...) -> AgentState`, `Components`, JSON-safe trace; state keys | Richer state routing, repair feedback, eventual LangGraph if useful; maintain repair/optimizer caps and ablation behavior | `pytest -q tests/test_orchestrator.py tests/test_config.py` |
| 2 | `SchemaRetriever.retrieve(question, top_k=5) -> str`, `retrieve_schema(...) -> str` | Graph creation/upload and selective Neo4j retrieval; flat versus graph experiment; keep offline fallback explicit | `pytest -q tests/test_schema.py`; `make schema-graph` |
| 3 | `check_syntax`, `check_safety`, `verify_semantics`, `verify_result` result keys | Semantic alignment, missing fields, assumptions, and question-aware result checks; replace placeholder statuses only when checks are real | `pytest -q tests/test_syntax.py tests/test_safety.py tests/test_semantic.py tests/test_result.py` |
| 4 | `optimize_sql` result keys, `explain_query_plan`, `compare_results` | Plan analysis, proposed rewrites, an equality gate before `changed=True`, and controlled before/after timing | `pytest -q tests/test_optimizer.py`; `make benchmark` |
| 5 | `run_evaluation`, metric denominator definitions, ablation switches; UI calls `run_querymind` | Evaluation datasets, experiment tables, b2 self-consistency, full ablation runs, grounded response/UI refinements | `pytest -q tests/test_metrics.py tests/test_ui.py`; `make eval`; `make ablation`; `make ui` |

`src/agents/generator.py` is a thin provider wrapper. `src/agents/response.py` is a
deterministic response formatter. Coordinate their later owners through integration;
they are outside the five primary ownership lists in the capstone request.

All developers run `pytest` before merging. Unit tests use temporary databases and
reject network access. Keep real Neo4j/model checks outside the default suite; place
future service tests under a separate `integration_tests/` directory with the
`integration` marker, and run them explicitly. Do not loosen the offline fixture
for ordinary tests. The `pytest.ini` testpaths currently includes only `tests/`.

An ablated syntax node still runs safety checks. SQLite's mode=ro, query_only and
authorizer protections are independent of every optional node. Never substitute a
writable executor to facilitate a feature. Neo4j connection credentials belong in
environment variables, never user question input or YAML.

## Create the five branches

Review the untracked foundation, then create the initial commit:

```bash
git status --short
git add .
git commit -m "Bootstrap QueryMind Milestone 2 foundation"
git branch feature/orchestrator
git branch feature/schema-graph
git branch feature/verifiers
git branch feature/optimizer
git branch feature/eval-ui
```

Each developer selects their branch in their own clone:

```bash
git switch feature/orchestrator  # substitute the assigned branch
source .venv/bin/activate
pytest
```

Publish branches only when ready. Merge shared integration changes first, then
feature implementations. Do not copy SQLite databases or generated traces between
branches as source; use the deterministic seeder and preserve any stakeholder
reproducibility artifacts if they are later added.
