"""R3: score the live ablation and report what is lost when each agent is removed.

Run with the stakeholder baseline's interpreter, like `score_report_eval.py`,
so correctness comes only from the pinned stakeholder scorer:

    external/agentic-sql-analyst/venv/bin/python scripts/score_ablation.py

For every variant and metric it reports the rate on r1 with a 95% Wilson
interval (stakeholder `score.wilson`), the change versus the full pipeline in
percentage points with a Newcombe hybrid-score interval (built from the two
Wilson intervals), the mean over repeats when there are several, and an exact
McNemar p-value on paired per-question correctness. Cost deltas (latency, LLM
calls, tokens) are descriptive. Writes eval/results/ablation/summary.json and
eval/results/ablation/ablation.md.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "eval/results/ablation"
FULL = "all_enabled"
VARIANT_ORDER = ("all_enabled", "without_neo4j", "without_semantic", "without_result_verifier",
                 "without_optimizer", "without_schema_retry", "without_syntax")
VARIANT_LABELS = {
    "all_enabled": "Full QueryMind", "without_neo4j": "- Neo4j retrieval (flat schema)",
    "without_semantic": "- Semantic verifier", "without_result_verifier": "- Result verifier",
    "without_optimizer": "- Optimizer", "without_schema_retry": "- Flat-schema retry",
    "without_syntax": "- Syntax verifier",
}
# (key, label, higher_is_better); keys are (k, n) pairs from rate_metrics().
RATE_METRICS = (
    ("correct_all", "Correct, all questions", True),
    ("set_easy", "Easy accuracy", True),
    ("set_hard", "Hard accuracy", True),
    ("unanswerable_refused_correctly", "Unanswerable refused + field named", True),
    ("fabrications", "Fabrications on unanswerable", False),
    ("ambiguity_flagged", "Ambiguity flagged", True),
    ("over_refusal", "Over-refusal", False),
    ("exec_success", "Execution success", True),
)
Wilson = Callable[[int, int], tuple[float, float]]


def newcombe(k1: int, n1: int, k2: int, n2: int, wilson: Wilson) -> tuple[float, float, float] | None:
    """Difference p1 - p2 in percentage points with the Newcombe hybrid-score 95% interval."""
    if not n1 or not n2:
        return None
    p1, p2 = 100 * k1 / n1, 100 * k2 / n2
    (l1, u1), (l2, u2) = wilson(k1, n1), wilson(k2, n2)
    diff = p1 - p2
    return (diff, diff - math.hypot(p1 - l1, u2 - p2), diff + math.hypot(u1 - p1, p2 - l2))


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def rate_metrics(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """(k, n) for each rate metric; definitions match score_report_eval.summarize."""
    def pair(items, pred=lambda r: bool(r["correct"])):
        return (sum(1 for r in items if pred(r)), len(items))

    unans = [r for r in rows if r["kind"] == "unanswerable"]
    out = {
        "correct_all": pair(rows),
        "set_easy": pair([r for r in rows if r["set"] == "easy"]),
        "set_hard": pair([r for r in rows if r["set"] == "hard"]),
        "unanswerable_refused_correctly": pair(unans),
        "fabrications": pair(unans, lambda r: not r["record"].get("refused") and bool(r["record"].get("exec_ok"))),
        "ambiguity_flagged": pair([r for r in rows if r["kind"] == "ambiguous"]),
        "over_refusal": pair([r for r in rows if r["kind"] in ("reference", "ambiguous")],
                             lambda r: bool(r["record"].get("refused"))),
        "exec_success": pair(rows, lambda r: bool(r["record"].get("exec_ok"))),
    }
    return {key: value for key, value in out.items() if value[1]}


def cost_metrics(rows: list[dict]) -> dict[str, float | None]:
    records = [r["record"] for r in rows if r["record"]]
    latency = sorted(r["latency_ms"] / 1000 for r in records if isinstance(r.get("latency_ms"), (int, float)))
    calls = [r["qm_llm_calls"] for r in records if isinstance(r.get("qm_llm_calls"), int)]
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in records
              if isinstance(r.get("prompt_tokens"), int) and isinstance(r.get("completion_tokens"), int)]
    return {
        "p50_latency_s": statistics.median(latency) if latency else None,
        "p95_latency_s": latency[max(0, math.ceil(0.95 * len(latency)) - 1)] if latency else None,
        "llm_calls_per_question": statistics.fmean(calls) if calls else None,
        "tokens_per_question": statistics.fmean(tokens) if tokens else None,
        "schema_retry_triggered": sum(1 for r in records if (r.get("qm_schema_retry") or {}).get("triggered")),
        "schema_retry_answered": sum(1 for r in records
                                     if (r.get("qm_schema_retry") or {}).get("outcome") == "answered"),
    }


def ablation_table(scored: dict[str, dict[str, list[dict]]], wilson: Wilson) -> dict:
    """scored = {repeat: {variant: [scored rows]}} -> per-variant rates, deltas and costs."""
    primary = scored.get("r1", {})
    if FULL not in primary:
        raise ValueError("r1 has no all_enabled traces; the full pipeline is the reference arm")
    full_rates = rate_metrics(primary[FULL])
    full_cost = cost_metrics(primary[FULL])
    full_correct = {(r["group"], r["id"]): bool(r["correct"]) for r in primary[FULL]}
    table = {}
    for variant in [v for v in VARIANT_ORDER if v in primary] + sorted(set(primary) - set(VARIANT_ORDER)):
        rows = primary[variant]
        rates = rate_metrics(rows)
        metrics = {}
        for key, (k, n) in rates.items():
            low, high = wilson(k, n)
            entry = {"k": k, "n": n, "rate": 100 * k / n, "wilson": [low, high]}
            if variant != FULL and key in full_rates:
                delta = newcombe(k, n, *full_rates[key], wilson)
                entry["delta_pp"] = list(delta) if delta else None
            per_repeat = [rate_metrics(scored[rep][variant]).get(key) for rep in sorted(scored)
                          if variant in scored[rep]]
            per_repeat = [100 * a / b for a, b in (p for p in per_repeat if p)]
            if len(per_repeat) > 1:
                entry["mean_over_repeats"] = statistics.fmean(per_repeat)
                entry["repeats"] = len(per_repeat)
            metrics[key] = entry
        cost = cost_metrics(rows)
        result = {"metrics": metrics, "cost": cost}
        if variant != FULL:
            mine = {(r["group"], r["id"]): bool(r["correct"]) for r in rows}
            keys = mine.keys() & full_correct.keys()
            lost = sum(1 for key in keys if full_correct[key] and not mine[key])
            gained = sum(1 for key in keys if mine[key] and not full_correct[key])
            result["paired_vs_full"] = {"n": len(keys), "lost": lost, "gained": gained,
                                        "p_exact_mcnemar": mcnemar_exact(lost, gained)}
            result["cost_delta"] = {key: (cost[key] - full_cost[key])
                                    if cost[key] is not None and full_cost[key] is not None else None
                                    for key in ("p50_latency_s", "p95_latency_s", "llm_calls_per_question",
                                                "tokens_per_question")}
        table[variant] = result
    return table


def markdown(dataset: str, table: dict) -> str:
    def rate(entry):
        return f"{entry['k']}/{entry['n']} ({entry['rate']:.0f}%; CI {entry['wilson'][0]:.0f}–{entry['wilson'][1]:.0f})"

    def delta(entry):
        d = entry.get("delta_pp")
        return f"{d[0]:+.0f} pp [{d[1]:+.0f}, {d[2]:+.0f}]" if d else "—"

    variants = list(table)
    lines = [f"## Ablation: {dataset}", "",
             "Each column switches one component off relative to the full pipeline. Cells: rate on r1 "
             "with 95% Wilson CI; below it, the change vs full in percentage points with a Newcombe "
             "95% CI. Arrows mark the better direction.", "",
             "| Metric | " + " | ".join(VARIANT_LABELS.get(v, v) for v in variants) + " |",
             "|---|" + "---:|" * len(variants)]
    for key, label, higher in RATE_METRICS:
        if not any(key in table[v]["metrics"] for v in variants):
            continue
        arrow = "↑" if higher else "↓"
        lines.append(f"| {label} {arrow} | " + " | ".join(
            rate(table[v]["metrics"][key]) if key in table[v]["metrics"] else "N/A" for v in variants) + " |")
        lines.append("| &nbsp;&nbsp;Δ vs full | " + " | ".join(
            delta(table[v]["metrics"][key]) if key in table[v]["metrics"] else "N/A" for v in variants) + " |")
    for key, label, fmt in (("p50_latency_s", "p50 latency (s)", "{:.1f}"),
                            ("p95_latency_s", "p95 latency (s)", "{:.1f}"),
                            ("llm_calls_per_question", "LLM calls / question", "{:.2f}"),
                            ("tokens_per_question", "Tokens / question", "{:.0f}")):
        lines.append(f"| {label} | " + " | ".join(
            fmt.format(table[v]["cost"][key]) if table[v]["cost"][key] is not None else "N/A"
            for v in variants) + " |")
    lines.append("| Flat-schema retries (triggered / answered) | " + " | ".join(
        f"{table[v]['cost']['schema_retry_triggered']} / {table[v]['cost']['schema_retry_answered']}"
        for v in variants) + " |")
    lines += ["", "| Variant | Paired n | Lost vs full | Gained vs full | exact McNemar p |",
              "|---|---:|---:|---:|---:|"]
    for v in variants:
        if "paired_vs_full" in table[v]:
            p = table[v]["paired_vs_full"]
            lines.append(f"| {VARIANT_LABELS.get(v, v)} | {p['n']} | {p['lost']} | {p['gained']} "
                         f"| {p['p_exact_mcnemar']:.3f} |")
    return "\n".join(lines)


def score_traces(dataset: str) -> dict[str, dict[str, list[dict]]]:
    """Score every ablation trace with the stakeholder scorer (needs its venv)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import score_report_eval as sre  # imports the stakeholder modules

    out: dict[str, dict[str, list[dict]]] = {}
    for repeat_dir in sorted((RESULTS / dataset).glob("r*")):
        per_variant = {}
        for trace in sorted(repeat_dir.glob("*__*.jsonl")):
            variant, group = trace.stem.split("__", 1)
            sources = {g: (q, d) for g, q, d in sre.sources(dataset)}
            questions_path, db_path = sources[group]
            questions = sre.dataset.index_by_id(sre.dataset.load_questions(str(questions_path)))
            records = {r["question_id"]: r for r in sre.load(trace)}
            conn = sre.db.connect(str(db_path))
            rows = []
            try:
                for qid, question in questions.items():
                    record = records.get(qid)
                    if record is None:
                        rows.append({"id": qid, "group": group, "set": question.set, "kind": question.kind,
                                     "correct": False, "verdict": "no trace record", "record": {}})
                        continue
                    try:
                        correct, verdict = sre.score.score_record(question, record, conn)
                    except RuntimeError as exc:
                        correct, verdict = None, f"unscored: {exc}"
                    rows.append({"id": qid, "group": group, "set": question.set, "kind": question.kind,
                                 "correct": correct, "verdict": verdict, "record": record})
            finally:
                conn.close()
            per_variant.setdefault(variant, []).extend(rows)
        out[repeat_dir.name] = per_variant
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=RESULTS / "summary.json")
    parser.add_argument("--markdown", type=Path, default=RESULTS / "ablation.md")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(PROJECT_ROOT / "external/agentic-sql-analyst/src"))
    import score  # stakeholder module: Wilson intervals

    report, sections = {"datasets": {}}, []
    for dataset in ("stakeholder60", "stakeholder"):
        if not (RESULTS / dataset).exists():
            continue
        scored = score_traces(dataset)
        table = ablation_table(scored, score.wilson)
        report["datasets"][dataset] = {"repeats": sorted(scored), "variants": table}
        sections.append(markdown(dataset, table))
    if not sections:
        parser.error(f"No ablation traces under {RESULTS}; run scripts/run_live_ablation.py first")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text("# R3 live ablation\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    print(args.markdown.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
