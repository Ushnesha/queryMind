# R7 handoff: verifier quality, example cards, second annotation

Read this first if you pull `milestone3/mem4_impl` (or `main` after it merges) and need to finish or
rerun this work.
Scope is analysis only: nothing under `src/` changes. Poster numbers must come from the
`poster-freeze` traces, never from hand typing.

## What exists

| Piece | File | Output |
|---|---|---|
| Semantic precision/recall and the 14 result-check firing rates | `scripts/analyze_verifiers.py` | `eval/results/verifier_semantic.csv`, `verifier_checks.csv`, `verifier_analysis.json` |
| "How we verify" panel (10.8 x 11 in vector PDF) | `scripts/make_verifier_figures.py` | `eval/results/poster/how_we_verify.pdf` |
| Example interactions strip, 3 cards (vector PDF) | `scripts/make_example_cards.py` | `eval/results/poster/example_interactions.pdf` |
| Member 4 questions (2 easy, 3 hard, 2 unanswerable, 1 ambiguous) | `eval/new_questions/member4.yaml` | none |
| Second-annotation template and agreement maths | `eval/annotations/member4_ambiguous.yaml`, `scripts/annotation_agreement.py` | `eval/results/annotation_agreement.json` |
| Tests | `tests/test_analyze_verifiers.py`, `test_make_verifier_figures.py`, `test_make_example_cards.py`, `test_annotation_agreement.py` | none |

## Rerun everything (Saturday, on the `poster-freeze` traces)

Needs the stakeholder baseline (`external/agentic-sql-analyst`, pinned `c0b0cda`) with its venv.
`make` is not installed on the Windows machine, so the Makefile steps were run by hand: clone,
`git checkout c0b0cda`, `uv venv --python 3.11 external/agentic-sql-analyst/venv`,
`uv pip install -r external/agentic-sql-analyst/requirements-dev.txt`, then
`venv/Scripts/python.exe scripts/seed_db.py --db ../../data/stakeholder_analytics.db`
(Linux and macOS use `venv/bin/python`).

```
PY=external/agentic-sql-analyst/venv/Scripts/python.exe     # venv/bin/python on Linux/macOS
$PY scripts/analyze_verifiers.py --traces <frozen traces dir> --out eval/results/
python scripts/make_verifier_figures.py
python scripts/make_example_cards.py --traces <frozen traces dir>
python -m pytest -q          # use this when `make` is missing; tests/test_ui.py needs streamlit
```

Then commit the two PDFs under `eval/results/poster/` (the scripts also write a PNG preview; do
not commit it unless the poster tool needs it). The scorer is only needed for the first command.

## Assumptions and decisions (all open to change; none confirmed by a teammate yet)

1. **Ground truth** is the stakeholder's unmodified scorer, called through
   `score_report_eval.score_dataset`. Nothing is re-scored by hand.
2. **Which traces:** arm `querymind`, run `r1` (the run the rest of the poster uses). Repeats
   r2 and r3 would count the same questions again.
3. **Mismatch verdict is a proxy.** The raw "SQL does not match" verdict is not stored in the
   traces. The orchestrator repairs exactly when it is raised, so `qm_repair_count > 0` stands in.
   Truth is "scorer marks the answer wrong", on reference questions only, and it judges the final
   SQL while the verdict was about the first SQL. State this on the poster. To get exact numbers,
   the owner of `src/` would have to log the raw verdict before the freeze.
4. **Not answerable:** flagged when `refused` and `missing_field` is set. Truth is `kind: unanswerable`.
5. **Assumption flagged:** flagged when `assumptions` is non-empty. Truth is `kind: ambiguous`.
   The stakeholder scorer itself counts a non-empty `assumptions` as correct on ambiguous questions.
6. **Spider is included by default.** Spider adds many reference questions, so precision for
   "not answerable" and "assumption flagged" is dominated by Spider over-refusals. Use
   `--datasets stakeholder` for a stakeholder-only view. Both are valid, so pick one for the
   poster, say which, and keep it fixed after the freeze.
7. **Result checks** use the executed answers as the denominator, because passes are not logged.
   A check "fires" when its code appears in `qm_result_warnings`. There are 14 codes
   (13 documented plus `MALFORMED_ROWS`).
8. **Small samples:** any rate with fewer than 5 cases is marked "too few examples" and the panel
   adds an asterisk. Wilson 95% intervals are in the CSV and JSON.
9. **Cards:** the third card is "Show sales trends over time" (plan Section 3). The layout sketch
   may mean the optimized-query card instead. Member 1 has not answered. The b0 contrast line on
   the profit-margin card is the result of running b0's recorded SQL read only against
   `data/stakeholder_analytics.db`, because the b0 trace stores SQL but not rows. Answers are
   cropped with "..." and never reworded. The strip is 22 x 10.7 in (taller than the shared 22 x 9)
   because the SQL needs it at 24 pt.
10. **Style:** figures use `scripts/poster_style.py` (Member 1, on `milestone3/mem1_impl`) when it
    exists and a local stand-in otherwise. Both scripts force the headless `Agg` backend.
11. **Second annotation is not done.** The labeling scheme is not published. The template assumes
    one label per ambiguous question: `measure`, `time` or `threshold`. `label` is empty on
    purpose: the second annotator must fill it in alone, and no hint labels are kept in the file. Only 9 of the plan's 10 ambiguous questions exist in
    the files so far.

## Known problems elsewhere (not fixed here, not my files)

- `eval/new_questions/member5.yaml` on `feature/optimizer_scale` targets the QueryMind demo
  schema (`name`, `amount`, `email`) in a different YAML format. The stakeholder scorer cannot
  load it. `M5_H3` also duplicates `M1-H3`.
- Member 2's merged `eval/questions_60.yaml` cites stakeholder commit `48beeaa`, but the scorer is
  pinned at `c0b0cda`. Questions and scorer must come from the same commit.
- The plan's table adds up to 40 new questions and 20 existing ones, not 43 and 17.
- `matplotlib` is imported by the figure scripts but is missing from `requirements.txt`.
- `tests/test_ui.py` fails to collect without `streamlit`.
- Merge `milestone3/mem4_impl` before `milestone3/mem2_impl`, which is stacked on `milestone3/mem1_impl`.
  Member 5's branch changes `src/optimizer`, so frozen traces may differ from today's.

## Still to do

1. Rerun on the `poster-freeze` traces (commands above) and commit the two PDFs.
2. Fill in `eval/annotations/member4_ambiguous.yaml` independently, get the first annotator's
   labels, run `scripts/annotation_agreement.py`, report raw agreement and kappa with counts.
3. Confirm the verdict definitions (items 3 to 6) with Member 1 and put them in a poster footnote.
4. Decide cards as vector PDF from this script or typeset in the poster tool.
