# QueryMind Milestone 2 — 4-Day Implementation Plan

> **Purpose:** This is the single implementation handoff document for all five team members. Start from the shared `milestone2` bootstrap branch, create your assigned feature branch, implement only your owned component, preserve the shared interfaces, add tests, and open a PR back to `milestone2`.

---

## 0. Milestone 2 Goal

By the end of Day 4, QueryMind must demonstrate a **working agentic Text-to-SQL system** and **preliminary evaluation results**.

The required end-to-end flow is:

```text
Natural-language question
        |
        v
Streamlit UI
        |
        v
Orchestrator
        |
        v
Schema retrieval (Neo4j or flat schema)
        |
        v
SQL Generator
        |
        v
Syntax + Safety Verifier
        | failure -> repair -> verify again (max 3 repairs)
        v
Semantic Verifier
        | missing data -> refuse and name missing field
        v
Query Optimizer
        | rewrite accepted only if results are equal
        v
Read-only SQLite execution
        |
        v
Result Verifier
        |
        v
Response Generator
        |
        v
Answer + result table + SQL + assumptions + verification + trace
```

The milestone is **not** intended to finish the entire final-project evaluation. The priority is a reliable vertical slice plus preliminary evidence.

### Must be demonstrated by Day 4

- Working Streamlit demo.
- Working orchestrated agent pipeline.
- SQL generation and repair.
- Read-only safety and syntax checking.
- Semantic verification, including missing-field/refusal behavior.
- Stronger result checking than only `empty` / `all zeros`.
- Neo4j schema representation/retrieval plus flat-schema alternative.
- Query-plan inspection and safe optimizer.
- Result-equality gate for optimizer rewrites.
- JSONL/structured execution traces.
- Existing `b1` baseline comparison.
- Small `b2` self-consistency experiment.
- Node-by-node ablation experiment.
- Preliminary Neo4j-vs-flat-schema experiment.
- Preliminary optimizer evaluation.

### Explicitly defer if time is insufficient

- Full 60-question repeated evaluation.
- Full Spider 1.0 evaluation.
- Full BIRD evaluation.
- Spider 2.0-Lite full evaluation.
- BEAVER full evaluation.
- Human evaluation.
- Second-model study.
- Large 300-table schema sweep.
- Production deployment or polished UI.

---

# 1. What the `milestone2` Branch Represents

`milestone2` is the **shared integration contract**.

It should contain the existing stakeholder baseline plus the QueryMind bootstrap skeleton. It is not expected to contain the completed Milestone 2 functionality yet.

The existing baseline should remain reusable for:

- read-only SQLite connection;
- schema introspection;
- LLM/provider abstraction;
- offline mock provider;
- SQL execution;
- scorer/result normalization;
- deterministic database seeding;
- JSONL traces;
- existing evaluation questions;
- existing tests.

The bootstrap should provide shared contracts similar to:

```text
src/
├── state.py
├── orchestrator.py
├── trace.py
├── run.py
├── agents/
│   ├── generator.py
│   └── response.py
├── schema/
│   ├── interface.py
│   ├── flat_retriever.py
│   ├── neo4j_retriever.py
│   └── build_graph.py
├── verifiers/
│   ├── safety.py
│   ├── syntax.py
│   ├── semantic.py
│   └── result.py
├── optimizer/
│   ├── explain.py
│   ├── optimizer.py
│   └── equality.py
└── evaluation/
    ├── runner.py
    ├── metrics.py
    ├── ablation.py
    └── b2.py

app.py
config/settings.yaml
docs/INTERFACES.md
docs/DEVELOPMENT.md
```

Before beginning feature development, every member must run:

```bash
git checkout milestone2
git pull origin milestone2
pytest
```

If existing baseline tests fail before your change, report that immediately. Do not silently rewrite baseline behavior.

---

# 2. Shared Contract — DO NOT BREAK

The purpose of the bootstrap is to let all five members work independently. Therefore, shared interfaces are APIs.

## 2.1 Shared Agent State

The shared state should contain approximately:

```python
class AgentState(TypedDict, total=False):
    question: str

    schema_mode: str
    schema_context: str

    sql: str
    sql_history: list[str]

    syntax_ok: bool
    syntax_error: str

    semantic_ok: bool
    semantic_reason: str

    answerable: bool
    missing_fields: list[str]
    assumptions: list[str]

    original_sql: str
    optimized_sql: str
    optimization_applied: bool

    original_plan: list
    optimized_plan: list

    rows: list
    columns: list[str]

    result_ok: bool
    result_warnings: list[str]

    final_answer: str

    repair_count: int
    optimizer_count: int

    trace: list[dict]
    metrics: dict
```

Do not put Neo4j driver objects, SQLite connections, model clients, DataFrames, or other non-serializable runtime objects in the shared state.

## 2.2 Public Component Interfaces

All members should preserve the bootstrap interfaces. If the actual repository interface differs slightly, follow `docs/INTERFACES.md` rather than creating a second API.

```python
retrieve_schema(question: str, mode: str = "neo4j") -> str

generate_sql(question: str, schema_context: str) -> str

check_syntax(sql: str) -> dict

verify_semantics(question: str, sql: str, schema_context: str) -> dict

optimize_sql(sql: str, question: str, schema_context: str) -> dict

execute_sql(sql: str) -> dict

verify_result(question: str, sql: str, rows: list, columns: list[str]) -> dict

generate_response(state: AgentState) -> str
```

## 2.3 Shared Files

Treat these as integration-owner controlled:

```text
src/state.py
config/settings.yaml
requirements.txt
Makefile
README.md
docs/INTERFACES.md
```

If you must change one, coordinate with Member 1 before doing so.

---

# 3. Team Ownership

| Member | Branch | Primary Responsibility | Owned Area |
|---|---|---|---|
| Member 1 | `feature/orchestrator` | Orchestration, SQL generation/repair, integration | `src/orchestrator.py`, `src/state.py`, `src/trace.py`, generator/response integration |
| Member 2 | `feature/schema-graph` | SQLite schema -> Neo4j, flat/graph retrieval | `src/schema/`, `scripts/build_schema_graph.py` |
| Member 3 | `feature/verifiers` | Safety, syntax, semantic and result verification | `src/verifiers/` |
| Member 4 | `feature/optimizer` | EXPLAIN, optimization, equality gate, timing | `src/optimizer/`, optimizer benchmark |
| Member 5 | `feature/eval-ui` | Streamlit, evaluation harness, b2, ablations | `app.py`, `src/evaluation/`, evaluation scripts |

Each member should avoid editing another member's owned files unless integration requires it and the owner agrees.

---

# 4. MEMBER 1 — Orchestrator + SQL Generator + Integration

## Branch

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/orchestrator
```

## Objective

Turn the bootstrap skeleton into the real QueryMind control loop. This member is also the final integration owner.

## Required workflow

```text
START
  |
  v
retrieve_schema
  |
  v
generate_sql
  |
  v
syntax_check <-------------------+
  |                              |
  +-- fail --> repair_sql --------+
  |
  v
semantic_check
  |
  +-- missing data --> refusal --> END
  |
  +-- semantic mismatch --> repair if appropriate
  |
  v
optimize
  |
  v
execute
  |
  v
result_verify
  |
  v
respond
  |
  v
END
```

### Limits

```text
Maximum SQL repairs: 3
Maximum optimizer rounds: 2
```

## Tasks

### M1.1 Implement SQL generation

Reuse the existing model/provider abstraction.

Input:

```text
question
schema_context
```

Expected behavior:

- SQLite SQL only.
- One `SELECT` or `WITH` query.
- Never invent identifiers outside supplied schema.
- Never generate writes.
- Allow `NOT_ANSWERABLE:<field>` when schema is insufficient.

Do not create a second independent OpenAI client if `src/llm.py` or an equivalent provider already exists.

### M1.2 Implement SQL repair

When syntax/schema validation fails, call the generator with:

```text
original question
schema context
previous SQL
exact verifier/SQLite error
```

Store every SQL version in `sql_history`.

### M1.3 Implement routing

The orchestrator must make conditional decisions rather than blindly execute every component.

Examples:

- Syntax failure -> repair.
- Missing field -> stop and refuse.
- Ambiguous but answerable -> continue and store assumption.
- Good query plan -> optimizer may return unchanged SQL.
- Retry limit reached -> return an honest unreliable-answer response instead of guessing.

### M1.4 Support ablation switches

The public entry point must support something equivalent to:

```python
run_querymind(
    question,
    schema_mode="neo4j",
    enable_syntax=True,
    enable_semantic=True,
    enable_optimizer=True,
    enable_result_verifier=True,
)
```

Member 5 needs this for node-by-node experiments.

### M1.5 Trace every stage

Every component invocation should append a JSON-serializable event such as:

```json
{
  "node": "semantic_verifier",
  "status": "pass",
  "latency_ms": 820.4,
  "iteration": 1,
  "reason": "SQL meaning matches question"
}
```

Track at minimum:

- node;
- status;
- latency;
- iteration/retry;
- concise reason;
- LLM call count if available.

### M1.6 Response generation

The final state should support:

- plain-English answer;
- SQL;
- rows/columns;
- assumptions;
- missing fields;
- verification warnings;
- trace.

## Tests Member 1 must add

- Happy-path routing.
- Syntax failure -> repair -> success.
- Repair limit reached.
- Semantic unanswerable -> refusal.
- Optimizer disabled.
- Semantic verifier disabled.
- Result verifier disabled.
- Trace contains expected node sequence.
- Offline test uses mocks; no live model required.

## Definition of Done

Member 1 is done when:

```text
[ ] Orchestrator executes the complete interface sequence.
[ ] SQL generation works through existing provider abstraction.
[ ] Repair loop is capped at 3.
[ ] Missing-data path refuses.
[ ] Ablation flags work.
[ ] Trace is generated.
[ ] Tests pass offline.
[ ] No other member's internal implementation is duplicated.
```

---

# 5. MEMBER 2 — Neo4j Schema Graph + Retrieval

## Branch

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/schema-graph
```

## Objective

Implement the schema subsystem and make it possible to experimentally compare Neo4j schema retrieval with the baseline flat schema.

Neo4j is **internal system design**, not user input.

## Tasks

### M2.1 Introspect SQLite

Reuse existing baseline introspection where possible.

Collect:

```sql
PRAGMA table_info(table_name);
PRAGMA foreign_key_list(table_name);
PRAGMA index_list(table_name);
PRAGMA index_info(index_name);
```

Represent:

```text
Table
Column
Index
```

Relationships:

```text
(Table)-[:HAS_COLUMN]->(Column)
(Column)-[:REFERENCES]->(Column)
(Table)-[:HAS_INDEX]->(Index)
(Index)-[:INDEXES]->(Column)
```

### M2.2 Build/rebuild Neo4j automatically

Implement:

```bash
python scripts/build_schema_graph.py
```

The graph must be reproducibly generated from SQLite. Do not manually maintain schema facts in Neo4j.

### M2.3 Implement FlatSchemaRetriever

Return a compact full-schema representation containing:

- tables;
- columns/types;
- primary keys where available;
- foreign keys;
- indexes if relevant.

### M2.4 Implement Neo4jSchemaRetriever

Given a question, return a relevant subgraph containing as much as practical:

- relevant tables;
- relevant columns;
- FK relationships;
- join paths;
- indexes.

For the current small schema, a simple retrieval strategy is acceptable. Do not spend all four days building sophisticated semantic retrieval.

### M2.5 Graceful fallback

Basic tests and the default offline path must not require a live Neo4j instance.

If Neo4j is unavailable, either:

- raise a clear integration-specific error, or
- fall back to flat retrieval if that is the configured behavior.

Do not silently produce an empty schema.

### M2.6 Retrieval instrumentation

Return/log metrics that Member 5 can evaluate:

```text
tables returned
columns returned
relationships returned
schema context length/tokens if available
retrieval latency
```

## Tests Member 2 must add

- SQLite introspection returns expected tables.
- Foreign-key relationship is correctly represented.
- Flat retriever returns expected schema text.
- Neo4j query-building/retrieval logic can be tested with mocks.
- Basic unit suite does not require Neo4j server.
- Unknown/irrelevant question fails gracefully or returns a documented fallback.

## Preliminary experiment supported by this member

Member 5 will run the final experiment, but Member 2 must make this possible:

```python
run_querymind(question, schema_mode="flat")
run_querymind(question, schema_mode="neo4j")
```

Measure:

| Metric | Flat | Neo4j |
|---|---:|---:|
| Result accuracy | TBD | TBD |
| Correct tables | TBD | TBD |
| Correct join path | TBD | TBD |
| Schema context size | TBD | TBD |
| Retrieval latency | TBD | TBD |

A tie on the current three-table database is a valid preliminary result. Do not force a Neo4j advantage.

## Definition of Done

```text
[ ] SQLite schema can be extracted automatically.
[ ] Graph can be rebuilt from SQLite.
[ ] Flat retriever works.
[ ] Neo4j retriever works.
[ ] Join/FK information is represented.
[ ] Retrieval metrics are available.
[ ] Unit tests do not require live Neo4j.
[ ] Public retrieval interface remains unchanged.
```

---

# 6. MEMBER 3 — Safety + Syntax + Semantic + Result Verification

## Branch

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/verifiers
```

## Objective

Build the trust layer. The project's central problem is not merely SQL syntax; it is silent semantic failure where executable SQL produces a convincing but wrong answer.

## Tasks

### M3.1 Safety verifier

Reject/guard against operations including:

```text
INSERT
UPDATE
DELETE
DROP
ALTER
CREATE
REPLACE
ATTACH
DETACH
writable PRAGMA
multiple statements
```

Important: keyword/string checking is only a readable front-line check. Preserve the baseline's actual safety boundaries where available:

```text
read-only SQLite connection
+
SQLite authorizer
+
progress/cost limit
```

### M3.2 Syntax/schema verifier

Use SQLite preparation/`EXPLAIN` or existing database helpers to detect:

- invalid syntax;
- nonexistent table;
- nonexistent column;
- ambiguous column;
- invalid function;
- other SQLite errors.

Return the exact error so Member 1 can repair the SQL.

Expected structure:

```python
{
    "ok": False,
    "error": "no such column: ..."
}
```

### M3.3 Semantic verifier

Input:

```text
question
schema context
SQL
```

Return structured output:

```python
{
    "matches_question": True,
    "answerable": True,
    "missing_fields": [],
    "assumptions": [],
    "reason": "..."
}
```

It must explicitly reason about:

- whether SQL answers the requested quantity;
- missing data/fields;
- hidden assumptions;
- ambiguity;
- semantic mismatch despite executable SQL.

Critical regression case:

```text
Question: What is the profit margin per category?
```

If cost information is absent, expected behavior is approximately:

```python
{
    "matches_question": False,
    "answerable": False,
    "missing_fields": ["cost"],
    "assumptions": [],
    "reason": "Profit margin requires cost information not present in the schema."
}
```

### M3.4 Stronger result verifier

The result check must go beyond only `empty` and `all zeros`.

Implement deterministic checks for at least:

#### Empty output

```text
EMPTY_RESULT
```

#### All numeric values zero

```text
ALL_ZERO_RESULT
```

#### NULL-heavy output

```text
NULL_HEAVY_RESULT
```

#### NaN/Infinity/non-finite numeric output

```text
NON_FINITE_VALUE
```

#### Unexpected duplicate rows

```text
DUPLICATE_ROWS
```

#### Question/result shape mismatch

Examples:

- `top 3` should normally return no more than 3 rows.
- `how many` should normally produce aggregate/scalar-like output.
- `average`, `sum`, `count`, `min`, `max` should include a suitable numeric output.

#### Compact semantic result check

Where feasible, send a compact representation containing:

```text
question
SQL
result columns
row count
small row sample/statistics
```

and determine whether the result plausibly represents the requested quantity.

This check is a warning/verification signal, not permission for the LLM to invent facts.

### M3.5 Return result statistics

Expected shape:

```python
{
    "ok": True,
    "warnings": [],
    "statistics": {
        "row_count": 3,
        "null_fraction": 0.0,
        "duplicate_rows": 0
    }
}
```

## Tests Member 3 must add

Safety:

- SELECT allowed.
- WITH allowed.
- INSERT rejected.
- UPDATE rejected.
- DELETE rejected.
- DROP rejected.
- multiple statements rejected.

Syntax:

- valid SQL passes.
- nonexistent column returns exact failure.
- malformed SQL fails.

Semantic:

- known answerable question passes.
- profit-margin/missing-cost case is refused.
- ambiguous case records assumption when testable.

Result:

- empty output warning.
- all-zero warning.
- NULL-heavy warning.
- duplicate warning.
- top-3 row-count warning.
- aggregate/non-numeric warning.

## Definition of Done

```text
[ ] Safety layer blocks writes.
[ ] Syntax errors are returned precisely.
[ ] Semantic verifier returns structured output.
[ ] Missing cost/profit-margin case is detected.
[ ] Assumptions can be recorded.
[ ] Result verifier contains multiple sanity checks.
[ ] All verifier tests run offline where possible.
[ ] Interfaces match the shared contract.
```

---

# 7. MEMBER 4 — Query Optimizer + Result Equality Gate

## Branch

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/optimizer
```

## Objective

Implement plan-driven optimization that never sacrifices correctness for speed.

## Tasks

### M4.1 EXPLAIN QUERY PLAN

Run:

```sql
EXPLAIN QUERY PLAN
<generated SQL>
```

Capture plan signals such as:

```text
SCAN
SEARCH
USING INDEX
USING COVERING INDEX
USE TEMP B-TREE
```

Return the raw plan plus parsed summary.

### M4.2 Determine whether optimization is needed

Avoid an unnecessary optimizer LLM call when the plan is already reasonable.

Possible triggers:

- full scan where an available index can reasonably help;
- repeated/correlated subquery;
- unnecessary DISTINCT;
- unnecessary ORDER BY/temp B-tree;
- poor join formulation;
- other obvious plan issue supported by the actual SQLite plan.

Do not claim SQLite's planner can be overridden in ways it cannot.

### M4.3 Generate candidate optimized SQL

If optimization is justified, provide the optimizer with:

```text
question
original SQL
schema context
index metadata
EXPLAIN QUERY PLAN output
```

Expected return:

```python
{
    "changed": True,
    "sql": "...",
    "reason": "...",
    "plan_before": [...],
    "plan_after": [...]
}
```

### M4.4 Mandatory result-equality gate

Execute both original and candidate SQL safely.

Use/reuse the stakeholder scorer's result normalization/equality semantics where possible.

Only accept the candidate if:

```python
results_equal(original_result, optimized_result) is True
```

Otherwise keep the original SQL.

Correctness rule:

```text
A faster query with different rows is a failed optimization.
```

### M4.5 Measure execution time

Record:

```text
execution_ms_before
execution_ms_after
```

Use repeated SQLite execution if needed to reduce noise, but keep the method simple and documented.

### M4.6 Return optimization metadata

Example:

```python
{
    "changed": True,
    "accepted": True,
    "sql": optimized_sql,
    "reason": "...",
    "plan_before": [...],
    "plan_after": [...],
    "execution_ms_before": 1.8,
    "execution_ms_after": 1.2,
    "results_equal": True
}
```

## Tests Member 4 must add

- EXPLAIN works for valid SELECT.
- Plan parser recognizes scan/search/index signals.
- Good plan returns unchanged SQL.
- Changed-result rewrite is rejected.
- Equal-result rewrite can be accepted.
- Equality comparison handles unordered result semantics consistently with existing scorer where applicable.
- Optimizer failure falls back safely to original SQL.

## Preliminary optimizer experiment

Prepare a script that can output:

| Metric | Value |
|---|---:|
| Queries tested | TBD |
| Rewrites proposed | TBD |
| Rewrites accepted | TBD |
| Rewrites rejected for inequality | TBD |
| Accepted rewrite equality | must be 100% |
| Plans improved | TBD |
| Median execution before | TBD |
| Median execution after | TBD |

The original small database may be too fast to show meaningful wall-clock improvement. In that case report plan changes and use the larger seeded database if already available/feasible.

## Definition of Done

```text
[ ] EXPLAIN QUERY PLAN works.
[ ] Plans are parsed into useful signals.
[ ] Optimizer can choose to keep original SQL.
[ ] Candidate rewrite can be generated when needed.
[ ] Equality gate is mandatory.
[ ] Changed-result rewrite is rejected.
[ ] Timing metadata is recorded.
[ ] Tests pass offline except explicitly marked live-model tests.
```

---

# 8. MEMBER 5 — Streamlit + Evaluation + b2 + Ablation

## Branch

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/eval-ui
```

## Objective

Make QueryMind demonstrable and produce reproducible preliminary evidence.

## Tasks

### M5.1 Complete Streamlit UI

The user interaction must be obvious:

```text
QueryMind

Ask a question about the database:
[ Who are the top 3 customers by total spending? ]

[ Ask QueryMind ]
```

After execution show:

```text
ANSWER
plain-English answer

RESULT TABLE
...

FINAL SQL
SELECT ...

ASSUMPTIONS
...

VERIFICATION
✓ read-only
✓ syntax
✓ semantic
✓ result
✓ optimization result preserved

[View Agent Trace]
```

For unanswerable questions, show a clear refusal and missing field, for example:

```text
QueryMind cannot reliably answer this question.

Missing field: cost

Profit margin requires cost information that is not present in the database.
```

The UI should call `run_querymind()` and display the shared `AgentState`; it should not reimplement business logic.

### M5.2 Implement evaluation runner

Support commands equivalent to:

```bash
python scripts/run_eval.py --arm b1
python scripts/run_eval.py --arm b2
python scripts/run_eval.py --arm querymind
```

Store one structured record per question, preferably JSONL.

Example:

```json
{
  "question_id": "H3",
  "arm": "querymind",
  "correct": true,
  "refused": true,
  "missing_field": "cost",
  "ambiguity_flagged": false,
  "llm_calls": 2,
  "latency_ms": 8450
}
```

### M5.3 Metrics

Calculate at least:

- execution/completion success;
- easy accuracy;
- hard accuracy;
- false-answer/fabrication rate;
- unanswerable refusal rate;
- ambiguity flagged rate;
- over-refusal;
- LLM calls/question;
- p50 latency;
- p95 latency.

Reuse the existing stakeholder scorer instead of inventing a conflicting correctness definition.

### M5.4 Implement `b2-small`

For this preliminary milestone, run self-consistency on approximately 5–10 strategically selected questions with `k=3`.

For each question:

```text
Question
   |
   +--> generation 1 --> result A
   +--> generation 2 --> result A
   +--> generation 3 --> result B
                         |
                         v
                majority result A
```

Use result-level agreement rather than string equality of SQL where possible.

Label this experiment clearly:

```text
b2-small preliminary experiment (k=3)
```

Do not present it as the final planned b2 configuration.

### M5.5 Node-by-node ablation

Use the orchestrator switches from Member 1.

Run approximately 10 representative questions:

```text
FULL QueryMind
FULL - semantic verifier
FULL - result verifier
FULL - optimizer
FULL with flat schema instead of Neo4j
```

If time allows, add syntax-verifier ablation only if it is meaningful/safe in the offline experiment.

Produce:

| Configuration | Accuracy | Fabrications | Ambiguity Flagged | p50 Latency |
|---|---:|---:|---:|---:|
| Full QueryMind | TBD | TBD | TBD | TBD |
| - Semantic | TBD | TBD | TBD | TBD |
| - Result verifier | TBD | TBD | TBD | TBD |
| - Optimizer | TBD | TBD | TBD | TBD |
| Flat schema | TBD | TBD | TBD | TBD |

### M5.6 Neo4j vs flat experiment

On approximately 8–10 join/schema-sensitive questions, compare only the schema mode while keeping other variables fixed.

Report:

| Metric | Flat | Neo4j |
|---|---:|---:|
| Result accuracy | TBD | TBD |
| Correct tables | TBD | TBD |
| Correct join path | TBD | TBD |
| Schema context size | TBD | TBD |
| Retrieval latency | TBD | TBD |

A null result (no measurable graph benefit on three tables) is valid.

### M5.7 Preliminary main comparison

First run the existing 17-question set before trying to expand the dataset.

Produce:

| Metric | b1 | b2-small | QueryMind |
|---|---:|---:|---:|
| Easy accuracy | actual | actual | actual |
| Hard accuracy | actual | actual | actual |
| Unanswerable refusal | actual | actual | actual |
| Ambiguity flagged | actual | actual | actual |
| Fabrications | actual | actual | actual |
| Over-refusal | actual | actual | actual |
| p50 latency | actual | actual | actual |
| Calls/question | 1 | ~3 | actual |

Never fill missing experimental values with expected numbers.

## Tests Member 5 must add

- Metrics from small synthetic trace set.
- b2 majority selection.
- Tie/no-majority behavior is deterministic/documented.
- Ablation configuration maps correctly to orchestrator flags.
- Streamlit module imports without requiring live credentials.
- Evaluation can score committed/offline traces.

## Definition of Done

```text
[ ] Streamlit asks a question and displays AgentState output.
[ ] Refusal is visibly different from normal answer.
[ ] Evaluation runner works.
[ ] Metrics are reproducible.
[ ] b2-small works.
[ ] Ablation runner works.
[ ] Flat-vs-Neo4j comparison can be run.
[ ] Results are saved as structured artifacts.
```

---

# 9. Four-Day Schedule

## DAY 1 — Independent implementation

### Entire team: first 30 minutes

Confirm:

```text
1. Everyone starts from the same milestone2 commit.
2. pytest passes or known failures are documented.
3. docs/INTERFACES.md is understood.
4. Nobody is changing shared contracts independently.
5. Everyone knows their owned files.
```

### Member 1

Target by end of Day 1:

```text
question -> schema interface -> generator -> placeholder verifier/optimizer -> response
```

with trace and ablation switches.

### Member 2

Target:

```text
SQLite -> introspection -> graph builder
FlatSchemaRetriever works
Neo4j retriever core works/mocked
```

### Member 3

Target:

```text
safety verifier
syntax verifier
basic semantic verifier
```

### Member 4

Target:

```text
EXPLAIN QUERY PLAN
plan parser
result equality utility
```

### Member 5

Target:

```text
Streamlit -> run_querymind() -> display state
basic evaluation runner
```

### End-of-Day-1 rule

Every member must:

```bash
pytest
git add .
git commit -m "<meaningful feature commit>"
git push origin <feature-branch>
```

Do not merge broken work merely to meet the schedule.

---

## DAY 2 — Complete components + first integration

### By noon

Member 1:

```text
[ ] generation
[ ] repair
[ ] routing
[ ] retry caps
[ ] traces
```

Member 2:

```text
[ ] graph builder
[ ] flat retrieval
[ ] Neo4j retrieval
[ ] retrieval metrics
```

Member 3:

```text
[ ] safety
[ ] syntax
[ ] semantic
[ ] result verifier
```

Member 4:

```text
[ ] EXPLAIN
[ ] optimization decision
[ ] candidate rewrite
[ ] equality gate
[ ] timing
```

Member 5:

```text
[ ] Streamlit
[ ] evaluation runner
[ ] b2-small core
[ ] metric calculations
```

### First merge window — Day 2 afternoon

Open PRs into `milestone2`.

Recommended integration order:

```text
1. Member 3 — verifiers
2. Member 2 — schema
3. Member 4 — optimizer
4. Member 1 — orchestrator/integration
5. Member 5 — UI/evaluation
```

After every merge:

```bash
git checkout milestone2
git pull origin milestone2
pytest
```

Fix integration failures immediately.

### Day 2 exit criterion — CRITICAL

The real integrated system must successfully process:

```text
Who are the top 3 customers by total spending?
```

through:

```text
question
-> schema
-> generator
-> syntax/safety
-> semantic
-> optimizer
-> execute
-> result verifier
-> response
-> Streamlit
```

Then test:

```text
What is the profit margin per category?
```

Expected behavior:

```text
semantic verifier detects missing cost
-> execution is skipped
-> system refuses
-> missing field "cost" is displayed
```

If these two cases do not work by end of Day 2, Day 3 morning is integration/debugging, not new feature development.

---

## DAY 3 — Preliminary Evaluation Day

Freeze major architecture changes.

### Experiment A — b1 vs QueryMind

Run the existing stakeholder 17-question set first.

Collect actual QueryMind values for:

```text
execution/completion success
easy accuracy
hard accuracy
unanswerable refusal
ambiguity flagged
fabrication
p50/p95 latency
LLM calls/question
```

### Experiment B — b2-small

Run:

```text
5–10 selected questions
k = 3
```

Compare b1, b2-small and QueryMind.

### Experiment C — Neo4j vs flat

Run approximately 8–10 schema/join-sensitive questions.

Keep everything except `schema_mode` fixed.

### Experiment D — node ablation

Run approximately 10 representative questions:

```text
Full QueryMind
- semantic verifier
- result verifier
- optimizer
flat schema instead of Neo4j
```

### Experiment E — optimizer

Run the optimizer benchmark and report:

```text
queries tested
rewrites proposed
rewrites accepted
result equality
plan improvements
execution timing before/after
```

### End of Day 3

System should be feature-frozen except for bugs.

No new frameworks. No architecture rewrite. No new agents.

---

## DAY 4 — Stabilization + final evidence

### Morning

Run:

```bash
pytest
```

Then rerun final versions of:

```text
b1
QueryMind
b2-small
ablation
Neo4j vs flat
optimizer benchmark
```

Save reproducible results/traces.

### Demo cases to prepare

#### Demo 1 — normal multi-table question

```text
Who are the top 3 customers by total spending?
```

Shows:

```text
schema retrieval
JOIN generation
verification
execution
answer
```

#### Demo 2 — unanswerable

```text
What is the profit margin per category?
```

Shows:

```text
missing-field detection
honest refusal
```

#### Demo 3 — ambiguous

Use an existing ambiguous evaluation question.

Shows:

```text
assumption detection
assumption displayed to user
```

#### Demo 4 — optimizer

Use the best example where:

```text
plan before != plan after
```

while:

```text
result before == result after
```

### Final repository evidence

By the end of Day 4, `milestone2` should contain or point to:

```text
[ ] Working Streamlit demo
[ ] Working orchestrator
[ ] SQL generator + repair
[ ] Flat schema retrieval
[ ] Neo4j schema retrieval
[ ] Safety/syntax verification
[ ] Semantic verification
[ ] Result verification
[ ] Query optimizer
[ ] Result equality gate
[ ] Response generation
[ ] JSONL/structured traces
[ ] b1 preliminary results
[ ] b2-small results
[ ] QueryMind preliminary results
[ ] Node ablation results
[ ] Neo4j-vs-flat results
[ ] Optimizer results
[ ] Passing tests
```

---

# 10. Git Workflow

No one develops directly on `main` or `milestone2`.

Start work:

```bash
git checkout milestone2
git pull origin milestone2
git checkout <your-feature-branch>
git merge milestone2
```

Before pushing:

```bash
pytest
git status
git diff
```

Commit small logical changes:

```bash
git add .
git commit -m "Implement semantic verifier structured output"
git push origin feature/verifiers
```

PR direction:

```text
feature/* -> milestone2
```

Only after Milestone 2 is stable should the team consider:

```text
milestone2 -> main
```

Do not merge feature branches directly into one another unless there is an exceptional reason.

---

# 11. Integration Rules

## Rule 1 — Do not change another member's interface silently

If an interface is insufficient, discuss it before modifying it.

## Rule 2 — Prefer adapters over breaking changes

If your internal implementation needs richer information, preserve the existing public call where possible and add optional structured metadata rather than forcing every branch to change.

## Rule 3 — Offline tests must stay offline

Normal `pytest` must not require:

- ASU API credentials;
- network access;
- running Neo4j.

Live/integration tests should be explicitly marked.

## Rule 4 — Preserve baseline scoring

Do not invent a new correctness definition if the stakeholder scorer already handles result comparison.

## Rule 5 — Do not fabricate experimental results

Use `TBD` until the experiment has run.

Negative results are acceptable.

Examples:

- Neo4j may not help on a three-table schema.
- Optimizer may not reduce measurable runtime on a tiny SQLite DB.
- b2 may perform similarly to QueryMind.
- Additional agents may increase latency.

These are findings, not reasons to alter the measurements.

---

# 12. Preliminary Evaluation Matrix

Member 5 owns the final aggregation, but all components must expose the required metrics.

## Main comparison

| Metric | b1 | b2-small | QueryMind |
|---|---:|---:|---:|
| Completion/execution success | TBD | TBD | TBD |
| Easy accuracy | TBD | TBD | TBD |
| Hard accuracy | TBD | TBD | TBD |
| Unanswerable refusal | TBD | TBD | TBD |
| False answers/fabrications | TBD | TBD | TBD |
| Ambiguity flagged | TBD | TBD | TBD |
| Over-refusal | TBD | TBD | TBD |
| LLM calls/question | 1 | ~3 | TBD |
| p50 latency | TBD | TBD | TBD |
| p95 latency | TBD | TBD | TBD |

## Node ablation

| Configuration | Accuracy | Fabrications | Ambiguity | p50 |
|---|---:|---:|---:|---:|
| Full QueryMind | TBD | TBD | TBD | TBD |
| - Semantic | TBD | TBD | TBD | TBD |
| - Result verifier | TBD | TBD | TBD | TBD |
| - Optimizer | TBD | TBD | TBD | TBD |
| Flat schema | TBD | TBD | TBD | TBD |

## Neo4j vs flat

| Metric | Flat | Neo4j |
|---|---:|---:|
| Result accuracy | TBD | TBD |
| Correct tables | TBD | TBD |
| Correct join path | TBD | TBD |
| Schema context size | TBD | TBD |
| Retrieval latency | TBD | TBD |

## Optimizer

| Metric | Result |
|---|---:|
| Queries tested | TBD |
| Rewrites proposed | TBD |
| Rewrites accepted | TBD |
| Rejected for changed result | TBD |
| Result equality for accepted rewrites | target 100% |
| Plans improved | TBD |
| Median execution before | TBD |
| Median execution after | TBD |

---

# 13. What the Milestone 2 Report Should Say

The report must distinguish three categories.

## Implemented and evaluated

Only list components for which actual code and preliminary evidence exist.

Example:

```text
Implemented:
- orchestrated QueryMind pipeline
- Streamlit UI
- syntax/safety verification
- semantic verification
- result verification
- Neo4j schema retrieval
- query optimizer

Evaluated:
- existing 17-question set
- b2-small on N questions
- ablation on N questions
- flat-vs-Neo4j on N questions
- optimizer on N queries
```

## Implemented but only partially evaluated

Example:

```text
The Neo4j retriever is implemented, but its current evaluation uses only the small stakeholder schema. Large-schema validation remains future work.
```

## Planned for final milestone

Possible items:

```text
full Sql-Test-Eval-60
public benchmarks
larger schema evaluation
larger optimizer timing database
three-run consistency study
human evaluation
final confidence intervals/statistical analysis
```

---

# 14. Stakeholder Feedback Checklist

Before submission, verify every comment has been addressed.

```text
[ ] Streamlit demo exists.
[ ] Report explains exactly how user asks a question and sees an answer.
[ ] Neo4j is described as internal design, not user input.
[ ] Node-by-node test exists.
[ ] Result checking is stronger than empty/all-zero only.
[ ] Neo4j vs plain/flat schema experiment exists.
[ ] Small b2 experiment exists.
[ ] 60-question expansion is correctly attributed to stakeholder proposal.
[ ] b1 as main baseline is correctly attributed to stakeholder proposal.
[ ] Existing baseline numbers are not presented as new QueryMind results.
```

---

# 15. Team Check-ins

With only four days, have two short check-ins each day.

## Morning

Each member answers:

```text
1. What exact interface/component am I finishing today?
2. Do I need any shared-contract change?
3. What will be PR-ready by the next integration window?
```

## Evening

Each member answers:

```text
1. What works now?
2. What tests pass?
3. What is blocked?
4. Is my branch safe to merge?
5. What does Member 1 need to know for integration?
```

---

# 16. Critical Milestone Gates

Use these gates instead of judging progress by number of files or commits.

```text
END OF DAY 1
============
All five components work independently against their interfaces.

          |
          v

DAY 2 NOON
==========
Feature branches are substantially complete and tested.

          |
          v

END OF DAY 2
============
One real answerable question works end-to-end through Streamlit.
Profit-margin question correctly refuses due to missing cost.

          |
          v

DAY 3 NOON
==========
Preliminary b1-vs-QueryMind results exist.

          |
          v

END OF DAY 3
============
b2-small, ablation, flat-vs-Neo4j, and optimizer preliminary results exist.
System is feature-frozen.

          |
          v

DAY 4 NOON
==========
All critical bugs fixed; tests pass; final experiments rerun.

          |
          v

END OF DAY 4
============
Working Streamlit demo
+ reproducible traces
+ preliminary evaluation tables
+ documented remaining work.
```

---

# 17. Final Definition of Done

Milestone 2 is ready when the team can demonstrate this sequence without manually editing code between questions:

1. Start QueryMind/Streamlit.
2. Ask: `Who are the top 3 customers by total spending?`
3. Show schema retrieval.
4. Show generated SQL.
5. Show safety/syntax verification.
6. Show semantic verification.
7. Show query-plan inspection/optimization decision.
8. Execute read-only SQL.
9. Show result verification.
10. Show answer, table, SQL, assumptions, and trace.
11. Ask: `What is the profit margin per category?`
12. Show refusal naming missing `cost`.
13. Demonstrate an ambiguous question with assumption reporting.
14. Show one optimizer before/after case with equal results.
15. Show preliminary b1 vs b2-small vs QueryMind results.
16. Show node-by-node ablation.
17. Show flat-schema vs Neo4j preliminary results.
18. Explain clearly what remains for the final project.

A smaller system that completes this sequence reliably is preferable to a larger collection of unfinished components.

---

# 18. Quick Start for Each Member

## Member 1

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/orchestrator
# Read: docs/INTERFACES.md
# Work: orchestrator + generator/repair + trace + integration
pytest
```

## Member 2

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/schema-graph
# Read: docs/INTERFACES.md
# Work: SQLite schema -> flat/Neo4j retrieval
pytest
```

## Member 3

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/verifiers
# Read: docs/INTERFACES.md
# Work: safety + syntax + semantic + result verifier
pytest
```

## Member 4

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/optimizer
# Read: docs/INTERFACES.md
# Work: EXPLAIN + optimizer + equality gate + timing
pytest
```

## Member 5

```bash
git checkout milestone2
git pull origin milestone2
git checkout -b feature/eval-ui
# Read: docs/INTERFACES.md
# Work: Streamlit + evaluation + b2 + ablation
pytest
```

---

## One rule for everyone

**Do not optimize for how much code your branch contains. Optimize for whether your component satisfies its shared interface, has tests, exposes the metrics needed for evaluation, and can be merged into the end-to-end system by the end of Day 2.**
