# Member 3: latency (R6), flat-schema retry (R1 route), ablation (R3)

Branch `milestone3/mem3_impl`, based on `milestone3/mem2_impl` (which already contains
Member 1's branch). Everything below runs offline in tests; the numbers need the live runs
listed at the end.

## R6: latency

Milestone 2 baseline from the committed traces (`eval/results/report/stakeholder/r*/querymind__main.jsonl`):
**p50 12.0 s / p95 39.1 s on answered questions**. The slowest run is H1 (205 rows, ~815
completion tokens, ~37 s): the answer writer was given 20 raw rows with no length limit and
described them one by one.

What changed:

- `src/agents/response.py`: the answer writer gets a **computed summary** (row count,
  per-column min/max/total/mean, peak and lowest row, first/last label) plus the **first 10
  rows**, is told to write at most 3 sentences and not to list every row, and its completion is
  capped at **160 tokens** (`RESPONSE_MAX_TOKENS`). Providers without a `max_tokens`
  parameter still work.
- `src/llm.py`: `OpenAICompatibleProvider.generate(..., max_tokens=None)` sends
  `max_tokens` only when given, so SQL generation is unchanged. `token_usage()` reads the
  cumulative counters.
- **Per-step time and tokens in every trace.** Each trace event that made a model call has
  `llm_calls`, `prompt_tokens` and `completion_tokens`. `metrics.node_latency_ms` and
  `metrics.node_tokens` sum them per step. The stakeholder record carries them as
  `qm_node_latency_ms` / `qm_node_tokens`.
- `scripts/analyze_latency.py` (`make latency`): before vs after, overall and on the same
  question IDs, p50/p95 (overall and answered), runs over 15 s, and mean time/tokens per step.
  Target check: p50 answered < 15 s.

Note: R1's retry makes some refusals slower (one extra flat attempt), so the **all-runs** p50
may rise. The target is the **answered-question** p50, as in the plan.

## R1: flat-schema retry (owner of `src/orchestrator.py`)

Implemented as specified in `docs/R1_SCHEMA_RETRY.md`. The generate → safety → syntax →
semantic loop is now one function, `generate_and_verify(budget)`, that runs once with the
Neo4j context and at most once more with the flat context. Tests are in `tests/test_schema_retry.py`
and cover every case in section 7 of the spec.

Decisions on the spec's open questions:

1. **Quota:** the retry gets its own budget, `orchestrator.schema_retry_max_repairs`
   (default **1**, valid 0..3, in `config/settings.yaml`). The worst case is
   `max_repairs + 1 + 2` = 6 generations instead of 8, which protects both the gateway quota
   and the latency target. Set it to 3 to get the spec's "fresh `max_repairs`".
2. **Full-schema Neo4j runs:** no retry when retrieval's `fallback_reason` starts with
   `"No identifier matches"`, because the context already holds every table.
3. **`missing_fields`:** the Neo4j attempt's list is kept, and the flat list is used only when
   the Neo4j list is empty (as in the spec). Revisit after the first evaluation.

`metrics.schema_retry` (`triggered`/`trigger`/`outcome`) is set on every run that reaches
retrieval and is written as `qm_schema_retry`.

## R3: live ablation

- `experiment_variants()` builds every variant from the full Neo4j arm, so each one changes
  exactly one key. The new variant is `without_schema_retry`.
- `scripts/run_querymind_trace.py --disable {syntax,semantic,optimizer,result_verifier,schema_retry}`.
  Read-only safety can never be disabled.
- `scripts/run_live_ablation.py` (`make ablation-live`, or `ablation-live-17` for 17 questions × 3)
  writes `eval/results/ablation/<dataset>/r<k>/<variant>__main.jsonl`. It is resumable and
  re-runs gateway failures. `all_enabled` and `without_neo4j` are **copied from the main
  evaluation's** `querymind` / `querymind-flat` traces, which saves 2 of the 6 configurations.
  Use `ABLATION_ARGS=--dry-run` to print the plan and the gateway cost first.
- `scripts/score_ablation.py` (`make ablation-score`, stakeholder venv) scores with the
  stakeholder's unchanged scorer. For each variant it gives the rate on r1 with a Wilson
  95% CI, the change vs full in pp with a Newcombe CI, the mean over repeats, and an exact
  McNemar test on paired correctness. Cost deltas are also reported. Output:
  `eval/results/ablation/ablation.md` and `summary.json`.

## Poster panels (`make member3-figures`)

All use `scripts/poster_style.py` and go to `eval/results/poster/`:

- `m3_architecture.pdf`: the 7-step pipeline, the repair loop (≤3), the R1 retry path (no
  longer "planned"), and the refusal exit. Box colour shows whether a step calls the LLM.
- `m3_latency.pdf`: mean time per answered question split by step (Milestone 2 has no split),
  plus p50/p95 against the 15 s target.
- `m3_ablation.pdf`: the change when each component is removed, for correct answers,
  avoiding over-refusal and avoiding fabrication. Every metric is oriented so that left means
  worse. A hollow dot means the CI includes 0.

A panel whose input JSON is missing is skipped, so the architecture can be drawn now.

## 60-question set

`eval/new_questions/member3.yaml` has 8 questions (2 easy, 3 hard, 2 unanswerable,
1 ambiguous), checked by `tests/test_member3_questions.py`. Member 2 merges them into
`eval/questions_60.yaml`.

## Still to run (needs the gateway, `.env`, seeded stakeholder DB and Neo4j)

1. Merge into main; then Member 1's `make report-eval-60` (QueryMind arms) writes the "after" traces.
2. `make latency`: check p50 answered < 15 s.
3. `make ablation-live ABLATION_ARGS=--dry-run`, then `make ablation-live`, then `make ablation-score`.
4. `make member3-figures`, then commit the PDFs from the `poster-freeze` data.
