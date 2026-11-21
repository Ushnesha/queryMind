# R1: Flat-schema retry for Neo4j-mode refusals

Owner of the code: Member 3 (`src/orchestrator.py`). Spec and review: Member 2.
Line numbers refer to `src/orchestrator.py` at commit `f454763`.

## 1. Goal

In `schema_mode="neo4j"` the retriever gives the model only the tables it ranks as
relevant. When it misses a needed table, the generator or the semantic verifier
concludes the data "doesn't exist" and QueryMind refuses an answerable question.
The FK-neighbour fix reduces this. The retry is the safety net: **before refusing
in Neo4j mode, retry once with the full flat schema, and accept the answer only if
it passes the same verification.**

Success criteria, measured on the stakeholder set (`eval/results/report/stakeholder/r1/`):

- Neo4j-mode over-refusal no higher than flat mode (Milestone 2: **6/11** Neo4j vs **3/11** flat).
- All **6 unanswerable** questions still refused.
- No fabricated answers: every answer from the retry passed safety, syntax and semantic verification.

## 2. When the retry triggers

All of the following must be true:

1. **Neo4j mode without flat fallback.** `mode == "neo4j"` (line 106) and the
   context does **not** contain `"Neo4j retrieval is a starter placeholder"` (the
   check at line 130). When `metrics.retrieval` is present, `backend != "flat_fallback"`
   is the same test. Do **not** use "`fallback_reason` is non-empty": the retriever
   also sets it on the `"No identifier matches; returned the full schema."` path
   (`src/schema/neo4j_retriever.py:76,102`), which is not a flat fallback. The
   marker check must stay, because an injected `Components.retrieve_schema` does
   not populate `metrics.retrieval` (line 115–116).
2. **The run is about to end as a refusal at one of three points** in the
   generate/verify loop:
   - (a) `not_answerable`: the generator returns `NOT_ANSWERABLE:...` (lines 145–148).
   - (b) `semantic_unanswerable`: the semantic verifier returns `answerable=False` (lines 186–188).
   - (c) `repairs_exhausted`: `repair_count >= max_repairs` (lines 202–204).
3. **The retry has not been used in this run.** At most one retry, ever.
4. **`enable_schema_retry` is `True`** (section 6).

It must **not** trigger on:

- **`status="error"`** (the `except` at line 262, result-verifier failure at
  257–258): an exception or gateway outage says nothing about the schema, and
  retrying would spend more quota against a failing service.
- **The generator's `ValueError` refusal (lines 141–143).** This is a fourth
  refusal point and is deliberately excluded: it carries provider failures
  (`"Provider HTTP error"` etc., `src/llm.py:161–171`) and the offline mock's
  "unsupported question", neither of which a bigger schema fixes. The stakeholder
  record already classifies it as `ProviderError`.
- **An empty question (lines 102–104):** it returns before retrieval; there is no
  schema to widen.
- **A refusal after execution:** none exists today. If one is added, it must not
  retry: the SQL has already run against a verified context, and a retry would
  execute twice and could swap a checked answer for a different one.

## 3. What the retry does

1. Fetch the flat context: `nodes.retrieve_schema(question, mode="flat",
   db_path=database_path, top_k=config.schema.top_k)` through `call_node("schema_retriever", ...)`
   so it is timed and its trace event is recorded. Call it through `nodes` so tests can inject it.
   Leave `metrics.retrieval`, `retrieved_tables` and `retrieved_join_paths`
   unchanged: they describe the Neo4j retrieval being evaluated.
2. Record a trace event before the flat generation:
   `add_trace(state, "schema_retry", "retry", 0.0, <triggering refusal reason>)`.
3. Re-enter the same generate → safety → syntax → semantic loop with the flat
   context and **`feedback = ""`**: no repair feedback from the Neo4j attempt (it
   was written against the wrong schema). Reset the per-attempt verdict fields
   (`status="success"`, `answerable=True`, `semantic_ok`, `syntax_ok`, `safety_ok`,
   `syntax_error`, `missing_fields`, `assumptions`) before the first flat generation.
4. **Decision: the retry gets a fresh repair budget of `max_repairs`.** Use a
   local per-attempt counter for the budget check at line 202. `state["repair_count"]`
   stays the **total repairs across both attempts** (it feeds `qm_repair_count`, a
   cost figure). Worst case is `2 × (max_repairs + 1)` generations plus semantic-judge
   calls, i.e. 8 generations at `max_repairs=3`; see open question 1.
5. **Iteration numbers.** Today `attempt = repair_count + 1` (line 135). With a
   cumulative `repair_count` that number would repeat across attempts. Use
   `state["metrics"]["generation_calls"]` after the increment at line 136 (equal
   today in a run without a retry), and the same base for the `repair` event's
   `iteration` (line 211). This keeps `iteration == 1` meaning "the first
   generation of the run", which `qm_first_attempt_ok` relies on.

`generation_calls` (line 136) and `llm_calls` (via `call_node`) then count the
retry's calls with no extra code. Keep it that way.

## 4. When the retry's answer is accepted

Only when the flat attempt reaches the `break` at line 198–199: safety passed,
syntax passed (if enabled), and semantic verification passed (`semantic_ok` and
`answerable`, if enabled), exactly as in a normal run. It then continues through
optimizer, executor and result verifier **unchanged**, with
`state["schema_context"]` set to the flat context so the optimizer, result
verifier and response see the schema the SQL was written against.

If the flat attempt also refuses (at any of (a), (b), (c), or the generator
`ValueError`), the run ends as a refusal:

- `semantic_reason` = the **original Neo4j refusal reason**, followed by
  `" Flat-schema retry also refused: <flat reason>"`. Appending keeps the
  `"SQL verification failed after the configured repair limit"` prefix that
  `to_stakeholder_record` uses for `RepairLimitReached`
  (`src/evaluation/stakeholder.py:73`).
- `missing_fields` = the **Neo4j attempt's** list, falling back to the flat
  attempt's list only when the Neo4j list is empty (e.g. trigger (c)). Reason:
  the reason text and the fields then come from the same attempt, so the response
  is coherent, and the unanswerable questions score informed refusal exactly as in
  the Milestone 2 Neo4j baseline (no regression on the 6). The fallback only adds
  information where the Neo4j attempt gave none.
- `assumptions` and `schema_context` are restored to the Neo4j attempt's values,
  for the same consistency.
- `status="refused"`, `answerable=False`, via `refuse()`.

## 5. What to record

- `state["metrics"]["schema_retry"] = {"triggered": bool, "trigger": "not_answerable" |
  "semantic_unanswerable" | "repairs_exhausted" | None, "outcome": "answered" |
  "refused" | None}`. Set it on **every** run that reaches retrieval, with
  `{"triggered": False, "trigger": None, "outcome": None}` when no retry happened, so
  aggregation never has to handle a missing key. `outcome="answered"` means the flat
  attempt passed verification (even if the result verifier later sets
  `status="error"`; that shows up in `qm_status`).
- The `schema_retry` trace event from section 3.2.
- A new field in `to_stakeholder_record`:
  `"qm_schema_retry": metrics.get("schema_retry")`, next to `qm_schema_fallback`.
  The poster counts `triggered` and `outcome == "answered"` from it.
- All values are plain strings, bools and `None`, so they are JSON-safe;
  `add_trace` already checks events with `json.dumps(..., allow_nan=False)`
  (`src/trace.py:28`).

## 6. Ablation switch

Add a keyword-only parameter `enable_schema_retry: bool = True` to `run_querymind`
(after `components`, line 51). `src/evaluation/ablation.py` needs it for R3:
`experiment_variants()` should gain a `"without_schema_retry"` variant
(`{**full, "enable_schema_retry": False}`). Leave `ablation_variants()` (the
four node switches used by the single-question smoke path) unchanged, since that
path runs in flat mode, where the switch has no effect.

## 7. Tests to add (`tests/test_orchestrator.py`)

Use `replace(Components(), ...)` with fake `retrieve_schema` that branches on
`mode` and returns a context **without** the placeholder marker for `"neo4j"`, and
fake `generate_sql` / `verify_semantics` keyed on the context they receive.

1. Neo4j refusal at each trigger (a), (b), (c) (parametrize), followed by a flat
   answer that passes: `status == "success"`, rows returned, `schema_context` is the
   flat one, `metrics.schema_retry == {"triggered": True, "trigger": <t>, "outcome": "answered"}`.
2. Flat attempt also refuses: `status == "refused"`, `semantic_reason` starts with
   the Neo4j reason and contains `"Flat-schema retry also refused"`, `missing_fields`
   follows section 4, `outcome == "refused"`.
3. An unanswerable question (both attempts `NOT_ANSWERABLE`) stays refused and
   never reaches `executor`.
4. Never a second retry: exactly one `schema_retry` event and two `schema_retriever`
   events, even when the flat attempt refuses.
5. `schema_mode="flat"` and a Neo4j run whose context contains the placeholder
   marker never retry (`triggered is False`, no `schema_retry` event).
6. `status="error"` never retries: a generator that raises a non-`ValueError`, and
   one that raises `ValueError("Provider HTTP error 500: ...")`.
7. `enable_schema_retry=False` refuses after the Neo4j attempt with no retry.
8. Trace event present with `status == "retry"` and the triggering reason, and
   `to_stakeholder_record(...)["qm_schema_retry"]` equals `metrics.schema_retry`;
   the whole state round-trips through `json.dumps`.

Also assert in (1) that `generation_calls` counts both attempts and that the
flat attempt's first `sql_generator` event has `iteration > 1`.

## 8. Out of scope

Changes to retrieval itself (`src/schema/`), the generator, judge or response
prompts, and the response generator. Re-running the stakeholder evaluation is a
follow-up once the PR is merged.

## 9. Open questions

1. **Quota.** A fresh budget doubles the worst case to 8 generations plus judge
   calls per question at `max_repairs=3`. Member 3 and Member 1: is that
   affordable on the gateway, or should the retry get `min(max_repairs, 1)`?
2. **Full-schema Neo4j runs.** When no seed table matches, retrieval already
   returns every table (`fallback_reason` starts with `"No identifier matches"`).
   A retry there sends the same schema again. Recommendation: skip the retry in
   that case; confirm with Member 3.
3. **`missing_fields` rule.** Section 4 keeps the Neo4j attempt's list to protect
   the unanswerable baseline. If the re-run shows the flat attempt names the
   missing field better, switch to the flat list. Decide after the first eval.

## 10. Resolution (Member 3, implementation)

1. Quota: the retry budget is `orchestrator.schema_retry_max_repairs` (default 1, range 0..3),
   so the worst case is `max_repairs + 1 + 2` generations. Set it to 3 for a fresh `max_repairs`.
2. Full-schema Neo4j runs: no retry when `fallback_reason` starts with `"No identifier matches"`.
3. `missing_fields`: as in section 4 (Neo4j list first, flat list only if it is empty).

Tests: `tests/test_schema_retry.py`. Details: `docs/MEMBER3.md`.
