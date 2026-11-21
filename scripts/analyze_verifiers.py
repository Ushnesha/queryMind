"""Verifier quality for the poster: semantic precision/recall and result-check firing rates.

Run with the stakeholder baseline's interpreter (the scorer needs it):

    external/agentic-sql-analyst/venv/Scripts/python.exe scripts/analyze_verifiers.py \
        --traces eval/results/report --out eval/results/

Ground truth comes from the stakeholder's unmodified scorer (`score.score_record`,
called through `score_report_eval.score_dataset`). Nothing is re-scored by hand.

DEFINITIONS (also the poster footnote). "Positive" means the verifier raised the flag.

  mismatch          verdict positive: the SQL was repaired at least once (qm_repair_count > 0).
                    The trace does not store the raw "SQL does not match" verdict, but the
                    orchestrator repairs exactly when that verdict is raised, so a repair is
                    our proxy. Truth positive: the scorer marks the final answer wrong.
                    Population: reference questions only (a wrong refusal is not a SQL mismatch).
                    Limit: truth is about the final SQL, the verdict was about the first SQL.
  not answerable    verdict positive: the run refused and named a missing field.
                    Truth positive: the question kind is "unanswerable".
  assumption        verdict positive: the answer states at least one assumption.
                    Truth positive: the question kind is "ambiguous".

Precision = TP / (TP + FP). Recall = TP / (TP + FN). Intervals are 95% Wilson.
A rate with fewer than MIN_EXAMPLES cases behind it is marked "too few examples".

Result checks: a check "fires" when its code appears in qm_result_warnings. Passes are not
logged, so the denominator is the answers that executed (exec_ok), split by scorer verdict.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIN_EXAMPLES = 5

CHECKS = (
    "EMPTY_RESULT", "ALL_ZERO_RESULT", "NULL_HEAVY_COLUMN", "NON_FINITE_VALUE",
    "ROW_LIMIT_EXCEEDED", "FEWER_ROWS_THAN_REQUESTED", "EXPECTED_SINGLE_ROW",
    "NON_NUMERIC_AGGREGATE", "NEGATIVE_COUNT", "DUPLICATE_ROWS", "DUPLICATE_COLUMNS",
    "UNKNOWN_RESULT_COLUMN", "SEMANTIC_CONTRADICTION", "MALFORMED_ROWS",
)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval in percent (same formula as the stakeholder's score.wilson)."""
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half) * 100, min(1.0, centre + half) * 100


def rate(k: int, n: int) -> dict:
    """Count, total, percent and interval. Empty when n is 0; flagged when n is small."""
    if n == 0:
        return {"k": k, "n": n, "pct": None, "ci_low": None, "ci_high": None, "too_few": True}
    low, high = wilson(k, n)
    return {"k": k, "n": n, "pct": 100 * k / n, "ci_low": low, "ci_high": high,
            "too_few": n < MIN_EXAMPLES}


def semantic_pairs(rows: list[dict]) -> dict[str, list[tuple[bool, bool]]]:
    """Per verdict, a list of (verifier flagged it, truth says it was real)."""
    scored = [r for r in rows if r["correct"] is not None]  # unscored rows have no truth
    return {
        "mismatch": [((r["record"].get("qm_repair_count") or 0) > 0, not r["correct"])
                     for r in scored if r["kind"] == "reference"],
        "not_answerable": [(bool(r["record"].get("refused")) and bool(r["record"].get("missing_field")),
                            r["kind"] == "unanswerable") for r in scored],
        "assumption_flagged": [(bool((r["record"].get("assumptions") or "").strip()),
                                r["kind"] == "ambiguous") for r in scored],
    }


def precision_recall(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(1 for flagged, real in pairs if flagged and real)
    fp = sum(1 for flagged, real in pairs if flagged and not real)
    fn = sum(1 for flagged, real in pairs if not flagged and real)
    tn = sum(1 for flagged, real in pairs if not flagged and not real)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn)}


def check_rates(rows: list[dict]) -> list[dict]:
    """For each result check: how often it fired on correct answers vs wrong answers."""
    ran = [r for r in rows if r["record"].get("exec_ok") and r["correct"] is not None]
    right = [r for r in ran if r["correct"]]
    wrong = [r for r in ran if not r["correct"]]

    def fired(code: str, row: dict) -> bool:
        return any(w.startswith(code + ":") for w in row["record"].get("qm_result_warnings") or [])

    return [{"check": code,
             "on_correct": rate(sum(fired(code, r) for r in right), len(right)),
             "on_wrong": rate(sum(fired(code, r) for r in wrong), len(wrong))}
            for code in CHECKS]


def analyze(rows: list[dict]) -> dict:
    return {"semantic": {name: precision_recall(p) for name, p in semantic_pairs(rows).items()},
            "result_checks": check_rates(rows)}


def load_scored(traces: Path, repeat: str, arm: str) -> tuple[list[dict], dict]:
    """Score the traces with the stakeholder scorer; return rows and a per-dataset count."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import score_report_eval as scorer  # imports the stakeholder's score.py; needs its interpreter

    scorer.RESULTS = traces
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for name in ("stakeholder", "spider"):
        if (traces / name).exists():
            part = scorer.score_dataset(name).get(repeat, {}).get(arm, [])
            counts[name] = len(part)
            rows += part
    return rows, counts


def cell(r: dict) -> str:
    if r["n"] == 0:
        return "n/a (0 cases)"
    text = f"{r['k']}/{r['n']} ({r['pct']:.0f}%, CI {r['ci_low']:.0f}-{r['ci_high']:.0f})"
    return text + (" too few examples" if r["too_few"] else "")


def write_outputs(result: dict, meta: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "verifier_analysis.json").write_text(
        json.dumps({"meta": meta, **result}, indent=2) + "\n", encoding="utf-8")
    with (out / "verifier_semantic.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["verdict", "tp", "fp", "fn", "tn", "precision", "recall"])
        for name, m in result["semantic"].items():
            w.writerow([name, m["tp"], m["fp"], m["fn"], m["tn"], cell(m["precision"]), cell(m["recall"])])
    with (out / "verifier_checks.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check", "fired_on_correct", "fired_on_wrong"])
        for c in result["result_checks"]:
            w.writerow([c["check"], cell(c["on_correct"]), cell(c["on_wrong"])])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--traces", type=Path, default=PROJECT_ROOT / "eval/results/report")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/results")
    parser.add_argument("--repeat", default="r1", help="run to analyse (default r1, as the rest of the poster)")
    parser.add_argument("--arm", default="querymind")
    args = parser.parse_args(argv)

    rows, counts = load_scored(args.traces.resolve(), args.repeat, args.arm)
    if not rows:
        parser.error(f"no {args.arm}/{args.repeat} traces found under {args.traces}")
    meta = {"traces": str(args.traces), "repeat": args.repeat, "arm": args.arm,
            "questions_per_dataset": counts, "min_examples": MIN_EXAMPLES}
    result = analyze(rows)
    write_outputs(result, meta, args.out)
    for name, m in result["semantic"].items():
        print(f"{name:<19} TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}  "
              f"precision {cell(m['precision'])}  recall {cell(m['recall'])}")
    for c in result["result_checks"]:
        print(f"{c['check']:<27} correct {cell(c['on_correct']):<40} wrong {cell(c['on_wrong'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
