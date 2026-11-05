# Bootstrap validation

Validated on November 4, 2026, using an isolated Python 3.11.15 environment.

## Before changes

The checkout contained only `.git`: no commits, tracked source, README, dependency
files, `src/`, `tests/`, `eval/`, baseline database, prompts, scorer, or traces.
There were **zero existing tests** and no baseline demo to run or reuse. No
stakeholder baseline artifacts were modified or deleted.

The requested initial test attempt was recorded before source changes:

- `python3 -m pytest -q`: the host Python 3.14.5 had no pytest module.
- `python -m pytest -q`: the host Anaconda Python 3.13.5 crashed during pytest
  initialization in `rlcompleter`/`pdb`, before collection.

An isolated `.venv` with Python 3.11.15 and the four pinned direct dependencies
resolved the environment issue. The existing global installations were unchanged.
The first integrated run needed the planned shared database fixture; after that
fixture was added, 63 tests passed. Review added three regression cases, yielding
the final total below. No test was removed, skipped, or weakened.

## Final suite

```text
Existing tests before: 0 (no baseline tests existed)
New tests:            66
Total tests after:    66
Passed:               66
Failed:               0
Skipped:              0
```

Command: `make test` (equivalent to `.venv/bin/python -m pytest -q`).
The entire default suite blocks socket connections and clears model credentials,
Neo4j credentials, and any external SQLite override. All database fixtures are
created in pytest temporary directories. No API key or Neo4j server is required.

Coverage includes shared state/configuration, replaceable nodes, bounded repairs,
semantic refusal, ablation switches, executor safety with checks disabled,
SQL parsing/compilation, schema retrieval, no-op optimization, duplicate-aware
scoring, UI contracts, JSONL traces, BLOB type preservation and nonfinite scalar
serialization. Tests verify code/contracts and deterministic mocks, not live model
answer quality.

## Runnable entry points

| Check | Result |
|---|---|
| `make seed` | Created the deterministic four-customer/six-order local fixture |
| `make baseline-demo` | New baseline returned the expected top three customers and spending totals |
| `make verify-data` | Customer count query returned 4 |
| `make demo` | `status=success`, 3 rows; strict JSONL trace saved |
| `python -m src.run --question "How many customers are there?" --schema-mode neo4j` | Success using visibly labeled flat-schema fallback |
| `make eval` / `make score` | Two reference-SQL cases matched, 2/2 |
| `make ablation` | Five single-question switch variants completed, 5/5 |
| `make schema-graph` | JSON metadata payload only; no Neo4j connection |
| `make benchmark` | Unchanged SQL, plan/timing metadata, equality comparison passed |
| `import app` | Streamlit entry point imported successfully |
| Streamlit `AppTest.from_file('app.py', default_timeout=30)` | Initial render and demo submission succeeded; 3 table rows, no exceptions |
| `python -m compileall -q src scripts app.py` | Successful |

The UI exercise used a disposable seeded SQLite file and no Streamlit server or
external service. Its first cold-start attempt exceeded AppTest's default three
seconds; allowing thirty seconds completed successfully. This was an import-time
test-runner timeout, not a query failure.

The evaluations above are smoke checks only. Semantic/result verification is
explicitly placeholder work, the optimizer does not rewrite SQL, graph retrieval
uses the offline fallback, and b2 is unimplemented.

## Repository review

`git diff --check` passed. Because the checkout began without tracked files,
there are no pre-existing baseline changes to compare. A foundation commit
appeared in the shared checkout during the work; it was preserved, with the
remaining handoff documentation left for review. No feature branches or remote
changes were made as part of validation.

Credential-pattern checks found no embedded secrets. `.env.example` contains blank
API/password values only. `.env`, the virtual environment, generated SQLite files,
JSONL logs, and generated evaluation reports are ignored. Source fixtures,
seed/schema scripts, and artifact `.gitkeep` files remain versionable.
