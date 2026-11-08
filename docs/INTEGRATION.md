# Integrated Milestone 2 validation

Validated November 8, 2026, with Python 3.11 and the existing local Neo4j service.
The implementation plan remains the design contract; this report describes the
merged code and the checks actually performed.

## Branches integrated

| Component | Branch tip included in main |
|---|---|
| Orchestration/generation | `origin/feature/orchestrate` — `eb62d2b` |
| Schema graph/retrieval | `origin/feature/schema-graph` — `e4bd657` |
| Optimizer | `origin/feature/optimizer` — `0c2414b` |
| Verifiers | `origin/feature/verifiers` — `7668be6` |
| Evaluation/UI | local `feature/eval-ui` — `0c784f5` |

Remote main already contained the first two components. The remaining three were
merged with merge commits. All feature history and historical reports are retained.

## Integration repairs

- Separate SQL generation attempts from measured model calls. The mock makes zero
  API calls; unknown provider counters stay unknown. Live generation and judge
  attempts use one provider counter, including unsuccessful API attempts.
- Route optimizer model requests through the shared provider. Offline optimizer
  triggers preserve the original SQL without loading credentials or making API calls.
- Pass the selected provider to semantic/result judges and preserve custom
  component injection. Result checking receives schema context.
- Handle `NOT_ANSWERABLE:` as an immediate refusal with missing fields and no repairs.
- Expose actual retrieval tables, FK join paths, backend and timing to evaluation.
  Preserve optimizer equality evidence for UI presentation.
- Load `.env` consistently at executable entry points. UI schema mode follows the
  configuration instead of forcing flat retrieval. Tests disable dotenv loading
  and reject network access.
- Make demo/UI targets explicitly select the seeded database. The existing `.env`
  selects a Spider database and is preserved. Reports use a separate ignored
  `eval/results/integrated/` directory rather than overwriting historical results.
- Update old orchestrator fixtures to supply semantically appropriate repair SQL
  and assert completed verification. Retain checks for repair limits and safety.

## Validation

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | 279 passed; none failed or skipped |
| Compile source, scripts and app | Passed |
| `make demo baseline-demo verify-data schema-graph` | Passed; customer count 4 and expected spending totals |
| Actual Neo4j schema upload | 2 tables, 7 columns, 1 FK relationship |
| Neo4j CLI demo | Success; actual `neo4j` backend, semantic/result checks pass |
| Streamlit HTTP health | HTTP 200, `ok` |
| Streamlit AppTest using local Neo4j | Count and top-three queries succeed; no UI exceptions |
| Paired b1/b2-small/QueryMind | 2/7 correct per arm; 0 actual LLM calls |
| Full 17-case b1/QueryMind | 2/17 correct per arm; no reference failures |
| Ablation | 10 questions × 6 configurations; 2/10 correct each |
| Flat vs actual Neo4j | 8 questions each; 1/8 correct each; zero fallbacks |
| Table and FK-path coverage | All annotated required tables and paths present in both modes |
| Spider optimizer benchmark | 30 queries across 3 databases; 0 rewrites in mock mode |
| `git diff --check` | Passed |

Table/path coverage measures inclusion, not retrieval precision. The two-table
demo produces identical full context in flat and graph modes. These measurements
do not establish a graph advantage or an optimizer speed improvement.

The 279 tests include five new cross-component regressions for shared provider
accounting, missing-cost refusal, generator refusal, offline optimizer triggers,
and retrieval metadata. Existing tests exercise real rewrite gates with injected
model replies; the default suite never requires external services.

## Run and inspect

```bash
make ui
make test
make eval
make ablation
make benchmark
.venv/bin/python -m scripts.run_eval --schema-comparison --db-path data/analytics.db --output eval/results/integrated/schema.json --markdown eval/results/integrated/schema.md
```

Streamlit is served at `http://localhost:8501`. Try “How many customers are there?”
or “Who are the top 3 customers by total spending?”. The latter returns Alice Chen
(300), Bob Smith (175), and Carol Davis (75).

The default model remains `mock`, which supports those two templates. Unsupported
questions are generic mock refusals and receive no informed-refusal credit. A
live provider must be selected in `config/settings.yaml` for broader questions
and live model-based verification/optimization. Credentials already present in
`.env` are preserved; no paid model calls were made during integration validation.

Fresh JSON, JSONL and Markdown reports are in `eval/results/integrated/`. Live
Neo4j demo state is also recorded in `logs/integrated_neo4j.jsonl`. These generated
artifacts are local and ignored. Historical branch reports remain unchanged.
