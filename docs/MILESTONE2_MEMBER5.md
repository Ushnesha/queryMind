# Member 5 — Milestone 2 implementation and preliminary evidence

Session date: November 5, 2026. Validation uses Python 3.11.15.

Member 5 deliverables are implemented: the Streamlit presentation, labelled reference-result evaluation, reduced b2 self-consistency, controlled node ablations, flat-versus-Neo4j comparison, JSON/JSONL artifacts, offline replay, and metrics/tests. The current shared pipeline still uses the deterministic MockProvider, placeholder semantic/result checks, a no-op optimizer, and a visible flat-schema fallback for Neo4j. These runs validate the experiment infrastructure and expose current coverage; they do not establish live-model accuracy or a benefit from graph retrieval, verification, optimization, or self-consistency.

## Scope and ownership

Implementation stays in `app.py`, `src/evaluation/`, and the two evaluation scripts. The shared state, orchestrator, schema/verifier/optimizer implementations, model settings, requirements, and scorer are preserved. Supporting changes add owned tests, a labelled question fixture, a synthetic replay fixture, and this report. The pre-existing untracked Spider download was not used or changed.

The checkout contained two demo questions, not the 17-question stakeholder set mentioned in the plan. `eval/questions.yaml` remains unchanged. The new `eval/milestone2.yaml` contains 17 seed-compatible preliminary cases: 13 answerable cases (including two ambiguous questions) and four unanswerable cases. Tags fix seven b2 cases, ten ablation cases, and eight schema cases. This fixture must not be described as the recovered stakeholder set.

## Streamlit demonstration

Launch with `.venv/bin/python -m streamlit run app.py`. Seed the default database first with `.venv/bin/python -m scripts.seed_db` if needed. Ask “Who are the top 3 customers by total spending?” or “How many customers are there?”. The UI displays Answer, Result, Generated SQL, Assumptions, Verification, and Agent Trace; output survives reruns. It renders supplied missing fields and refusal reasons, distinguishes unrun/disabled/placeholder checks from passes, and labels unchanged optimizer SQL separately from proven result preservation.

The mock currently refuses unsupported questions without identifying missing database fields. The profit-margin demo will display “Missing field: product cost” when the integrated provider/verifier supplies that field in AgentState. Member 5 does not infer a missing field from question keywords. UI tests exercise the supplied missing-field refusal state without pretending the current shared verifier implements that reasoning.

## Paired b1 / b2-small / QueryMind experiment

**b2-small preliminary experiment (k=3)** is reduced from the final proposed k=5 configuration. Every arm uses the same seven IDs: E1, E3, H1, H2, H3, U1, A1. B2 runs exactly three generation attempts per question, executes each through the shared read-only executor, and votes on the shared scorer’s normalized result multiset. A result needs more than half of all requested samples. Failed candidates cannot vote; ties/pluralities abstain. The first candidate in a strict winning group supplies the SQL. Explicit missing-field refusal consensus is separately recorded.

| Arm | Correct / scored | Accuracy | Generations/Q | Actual LLM calls/Q | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| b1 | 2/7 | 28.6% | 1.000 | 0.000 | 0.846 | 2.339 |
| b2-small | 2/7 | 28.6% | 3.000 | 0.000 | 0.837 | 3.507 |
| querymind | 2/7 | 28.6% | 1.000 | 0.000 | 0.880 | 2.196 |

Identical mock samples produce agreement by construction. There is no measured accuracy gain from b2 in this run. Its added generation attempts are visible, while actual LLM calls are zero. Single local timings at this scale do not support a latency ranking.

The full 17-question fixture runs only b1 and QueryMind; b2 is intentionally excluded. Both achieve 2/17 (11.8%) because the mock supports only the customer-count and top-N-spending templates. These are baseline coverage limits, not evidence that the agent design fails or succeeds with a live model.

| Metric on paired 7 cases | b1 | b2-small | QueryMind |
|---|---:|---:|---:|
| Easy accuracy | 50.0% | 50.0% | 50.0% |
| Hard accuracy | 20.0% | 20.0% | 20.0% |
| Completion | 28.6% | 28.6% | 28.6% |
| Informed unanswerable refusal | 0.0% | 0.0% | 0.0% |
| Raw unanswerable refusal | 100.0% | 100.0% | 100.0% |
| Fabrication proxy | 0.0% | 0.0% | 0.0% |
| Ambiguity flagged | 0.0% | 0.0% | 0.0% |
| Over-refusal | 66.7% | 66.7% | 66.7% |

Zero fabrications here reflects abstention, not evidence of semantic-verifier quality. The distinction between raw refusal and informed refusal prevents generic mock “unsupported” responses from being credited for detecting absent cost data.

## Node-by-node ablation

Ten fixed question IDs: E1, E2, E3, H1, H2, H3, H4, U1, U2, A1. Each variant changes one flag from the full Neo4j configuration. Syntax ablation is included; executor safety remains active in every variant.

| Configuration | Accuracy | Fabrication proxy | Ambiguity flagged | p50 ms |
|---|---:|---:|---:|---:|
| Full QueryMind | 20.0% | 0.0% | 0.0% | 0.879 |
| − Neo4j (flat schema) | 20.0% | 0.0% | 0.0% | 0.998 |
| − Semantic verifier | 20.0% | 0.0% | 0.0% | 0.889 |
| − Result verifier | 20.0% | 0.0% | 0.0% | 0.990 |
| − Optimizer | 20.0% | 0.0% | 0.0% | 0.791 |
| − Syntax verifier | 20.0% | 0.0% | 0.0% | 0.860 |

All variants score 2/10. The current placeholders, no-op optimization, and schema fallback prevent a scientific conclusion about whether each completed node earns its complexity. Re-run the same fixture after the other members integrate their components; keep null findings if they persist.

## Flat-versus-Neo4j comparison

Eight schema/join-sensitive IDs: H1, H2, H3, H4, H5, H6, A1, A2. All other pipeline options stay fixed.

| Metric | Flat | Neo4j mode |
|---|---:|---:|
| Result accuracy | 12.5% | 12.5% |
| Correct tables | N/A | N/A |
| Correct join path | N/A | N/A |
| Mean schema context characters | 285.000 | 356.000 |
| Mean retrieval latency ms | 0.429 | 0.335 |
| Fallback runs | 0.000 | 8.000 |

All eight Neo4j-mode runs use the disclosed flat fallback. Extra context characters include the fallback annotation; they do not measure graph selectivity. Table/join accuracy stays N/A until the retriever supplies `metrics.retrieved_tables` and `metrics.retrieved_join_paths`, compared with the fixture’s explicit annotations.

## Metric definitions and boundaries

- Accuracy: boolean reference outcomes only; exact column labels and unordered JSON row multisets, preserving duplicates/types. Row order and numeric tolerance are not scored. Informed missing-field refusals are correct on labelled unanswerable cases. Reference SQL errors remain unscored and are counted visibly.
- Easy/hard accuracy: correct / scored within the labelled difficulty. Missing subgroup observations yield N/A.
- Completion: `status=success` / all runs. Execution success measures successful execution for the selected final answer, not the fraction of b2 candidate executions. Candidate outcomes remain saved separately.
- Fabrication proxy: successful answers on labelled unanswerable cases / labelled unanswerable cases. This is not a prose hallucination judge.
- Informed refusal: correct missing-field refusals / labelled unanswerable cases. Raw refusal includes unsupported-provider abstentions.
- Ambiguity flagged: explicit ambiguity signals or assumptions from a completed semantic check / labelled ambiguous cases. Placeholder disclaimers receive no credit. A1 assumes best = top three by spending; A2 assumes usually = mean order amount for customers with orders. Other valid interpretations require adjudication.
- Over-refusal: refusals / labelled answerable cases.
- Calls/Q: averages of instrumented actual LLM counts only; unknown counts remain null. Confirmed mocks make zero LLM calls. Generation attempts are reported separately, including failed attempts.
- Latency: inference wall time, including retrieval and voting, excluding reference execution/scoring. p50/p95 use linear interpolation over finite recorded values; missing times do not become zero.

## Reproduce and inspect

Run from the repository root:

```bash
.venv/bin/python -m scripts.seed_db
.venv/bin/python -m streamlit run app.py
.venv/bin/python -m scripts.run_eval --arm b1
.venv/bin/python -m scripts.run_eval --arm b2
.venv/bin/python -m scripts.run_eval --arm querymind
.venv/bin/python -m scripts.run_eval --arm all --output eval/results/member5_comparison.json --markdown eval/results/member5_comparison.md
.venv/bin/python -m scripts.run_ablation --include-syntax --output eval/results/member5_ablation.json --markdown eval/results/member5_ablation.md
.venv/bin/python -m scripts.run_eval --schema-comparison --output eval/results/member5_schema.json --markdown eval/results/member5_schema.md
.venv/bin/python -m scripts.run_eval --arm querymind --traces eval/results/member5_comparison.jsonl --trace-experiment comparison --output eval/results/member5_replay.json
.venv/bin/python -m pytest -q
```

Both direct script invocation (`python scripts/run_eval.py`) and module invocation are supported. Each report writes strict JSON plus sibling JSONL; `--markdown` adds presentation tables. B2 defaults to the seven tagged cases and the CLI rejects populations above ten. `--db-path` and `--questions` select a disposable database/fixture. `--subset`/`--limit` control a deliberate subset. `--traces` scores saved states/cases without generation; select `--trace-experiment` and, for ablations, `--trace-configuration` to keep paired populations distinct. Missing expected traces stay visible and unscored. Do not merge experiment groups.

Python APIs accept the existing SQLProvider through `run_evaluation(..., provider=...)`; no second model client or live credential requirement is introduced. `run_options` forwards public orchestrator options for integration. The existing two-question smoke fixture remains usable with `--questions eval/questions.yaml`.

| Artifact | Contents |
|---|---|
| `eval/results/member5_comparison.json` / `.jsonl` / `.md` | Paired seven-case comparison and full b1/QueryMind 17-case coverage |
| `eval/results/member5_ablation.json` / `.jsonl` / `.md` | Ten questions × six configurations, including optional syntax ablation |
| `eval/results/member5_schema.json` / `.jsonl` / `.md` | Eight questions × two schema modes; fallback counts and missing instrumentation |
| `eval/fixtures/member5_traces.jsonl` | Explicitly synthetic committed scoring fixture, not model results |

Generated JSON/JSONL reports follow the repository’s existing ignore rules. This report and question/synthetic fixtures are versionable. Preserve JSONL files with a presentation submission if reviewers need to replay the measurements.

## Validation

Baseline: 66 tests passed before changes. Final suite: **115 passed**, zero failed/skipped. Tests block external sockets and use disposable seeded databases. Coverage includes synthetic metric denominators, finite latency percentiles, result-level majority and tie abstention, failed candidate voting, informed refusal consensus, call instrumentation, one-factor ablation flags, reference failures, committed trace replay, combined-report group selection, missing traces, JSON artifact destinations, malformed trace input, and Streamlit AppTest submission/refusal/rerun behavior. Unit tests validate deterministic code/contracts; they are not live model-quality evidence.

All three preliminary experiment commands completed. Full/paired reports have no reference SQL failures or unscored cases. No live LLM or Neo4j calls were made.

### Fixture fingerprints

- `eval/milestone2.yaml` SHA-256: `31758df3031ba73c9c3a576627b8481e4675bed4378a59ebb9ce402a33d2da1b`
- `data/analytics.db` SHA-256: `dc0025a0a04cfe606c5ed6261e9e7f4329c7878536ee660dcfb958bc993b709b`
