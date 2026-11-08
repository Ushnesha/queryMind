"""Score report traces with the stakeholder's unchanged decision rules.

Run with the stakeholder baseline's interpreter so that scoring depends only on
the pinned stakeholder code, never on QueryMind modules:

    external/agentic-sql-analyst/venv/bin/python scripts/score_report_eval.py

Correctness per record comes from `score.score_record` and intervals from
`score.wilson` (external/agentic-sql-analyst/src/score.py). This script only
aggregates, adds behaviour/cost metrics, and writes JSON plus Markdown tables.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SRC = PROJECT_ROOT / "external/agentic-sql-analyst/src"
sys.path.insert(0, str(BASELINE_SRC))

import dataset  # noqa: E402  (stakeholder module)
import db  # noqa: E402  (stakeholder module)
import score  # noqa: E402  (stakeholder module)

RESULTS = PROJECT_ROOT / "eval/results/report"
ARMS = ("b0", "b1", "querymind", "querymind-flat")
ARM_LABEL = {"b0": "b0 (frozen single call)", "b1": "b1 (b0 + refusal sentence)",
             "querymind": "QueryMind (Neo4j schema)", "querymind-flat": "QueryMind, flat schema (diagnostic)"}
PAIRS = (("querymind", "b0"), ("querymind", "b1"), ("querymind-flat", "b1"), ("querymind", "querymind-flat"))
INFRA_ERRORS = {"APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError",
                "APIStatusError", "ProviderError"}


def sources(name: str) -> list[tuple[str, Path, Path]]:
    if name == "stakeholder":
        return [("main", PROJECT_ROOT / "external/agentic-sql-analyst/eval/questions.yaml",
                 PROJECT_ROOT / "data/stakeholder_analytics.db")]
    root = PROJECT_ROOT / "data/spider_data/database"
    return [(p.stem, p, root / p.stem / f"{p.stem}.sqlite")
            for p in sorted((PROJECT_ROOT / "eval/spider_pilot/questions").glob("*.yaml"))]


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_attempt(sql: str) -> bool:
    return bool(sql) and bool(db.FORBIDDEN.search(db.strip_literals_and_comments(sql)))


def pct(k: int, n: int) -> str:
    if not n:
        return "N/A"
    low, high = score.wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%; CI {low:.0f}–{high:.0f})"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs b, c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def score_dataset(name: str) -> dict:
    """Return {repeat: {arm: [scored rows]}} for one dataset."""
    out: dict[str, dict[str, list[dict]]] = {}
    for repeat_dir in sorted((RESULTS / name).glob("r*")):
        per_arm: dict[str, list[dict]] = {}
        for arm in ARMS:
            rows = []
            for group, questions_path, db_path in sources(name):
                questions = dataset.index_by_id(dataset.load_questions(str(questions_path)))
                records = {r["question_id"]: r for r in load(repeat_dir / f"{arm}__{group}.jsonl")}
                if not records:
                    continue
                conn = db.connect(str(db_path))
                try:
                    for qid, question in questions.items():
                        record = records.get(qid)
                        if record is None:
                            rows.append({"id": qid, "group": group, "set": question.set, "kind": question.kind,
                                         "missing": True, "correct": False, "verdict": "no trace record",
                                         "record": {}})
                            continue
                        try:
                            correct, verdict = score.score_record(question, record, conn)
                        except RuntimeError as exc:
                            correct, verdict = None, f"unscored: {exc}"
                        rows.append({"id": qid, "group": group, "set": question.set, "kind": question.kind,
                                     "missing": False, "correct": correct, "verdict": verdict, "record": record})
                finally:
                    conn.close()
            if rows:
                per_arm[arm] = rows
        out[repeat_dir.name] = per_arm
    return out


def summarize(rows: list[dict], name: str) -> dict:
    recs = [r["record"] for r in rows]
    n = len(rows)
    refused = [r for r in rows if r["record"].get("refused")]
    attempted = [r for r in rows if not r["record"].get("refused")]
    answerable = [r for r in rows if r["kind"] in ("reference", "ambiguous")]
    reference = [r for r in rows if r["kind"] == "reference"]
    unans = [r for r in rows if r["kind"] == "unanswerable"]
    ambig = [r for r in rows if r["kind"] == "ambiguous"]
    lat = sorted(r["latency_ms"] / 1000 for r in recs if r.get("latency_ms") is not None)
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in recs
              if r.get("prompt_tokens") is not None and r.get("completion_tokens") is not None]
    calls = [r.get("qm_llm_calls", 1 if r.get("arm") in ("b0", "b1") else None) for r in recs]
    calls = [c for c in calls if isinstance(c, int)]

    def count(items, pred=lambda r: r["correct"]):
        return sum(1 for r in items if pred(r))

    s = {
        "n": n,
        "exec_success": (count(rows, lambda r: r["record"].get("exec_ok")), n),
        "exec_success_when_attempted": (count(attempted, lambda r: r["record"].get("exec_ok")), len(attempted)),
        "refusals": len(refused),
        "answer_accuracy_reference": (count(reference), len(reference)),
        "over_refusal": (count(answerable, lambda r: r["record"].get("refused")), len(answerable)),
        "assumptions_on_reference": (count(reference, lambda r: bool((r["record"].get("assumptions") or "").strip())),
                                     len(reference)),
        "infra_errors_remaining": count(rows, lambda r: r["record"].get("error_type") in INFRA_ERRORS),
        "missing_records": count(rows, lambda r: r["missing"]),
        "write_attempts": count(rows, lambda r: write_attempt(r["record"].get("sql") or "")),
        "latency_s": {
            "n": len(lat),
            "p50": statistics.median(lat) if lat else None,
            "p95": lat[max(0, math.ceil(0.95 * len(lat)) - 1)] if lat else None,
            "over_15s": sum(1 for x in lat if x > 15),
        },
        "tokens_per_question": statistics.fmean(tokens) if tokens else None,
        "token_records": len(tokens),
        "llm_calls_per_question": statistics.fmean(calls) if calls else None,
    }
    for label in sorted({r["set"] for r in rows}):
        chosen = [r for r in rows if r["set"] == label]
        s[f"set_{label}"] = (count(chosen), len(chosen))
    if unans:
        s["unanswerable_refused_correctly"] = (count(unans), len(unans))
        s["fabrications"] = (count(unans, lambda r: not r["record"].get("refused") and r["record"].get("exec_ok")),
                             len(unans))
    if ambig:
        s["ambiguity_flagged"] = (count(ambig), len(ambig))
    return s


def querymind_behaviour(all_rows: list[dict]) -> dict:
    recs = [r["record"] for r in all_rows if r["record"]]
    repaired = [r for r in recs if (r.get("qm_repair_count") or 0) > 0]
    first_fail = [r for r in recs if r.get("qm_first_attempt_ok") is False]
    errors = Counter(r.get("error_type") for r in recs if r.get("error_type"))
    return {
        "runs": len(recs),
        "first_attempt_verification_failures": len(first_fail),
        "runs_with_repairs": len(repaired),
        "repairs_recovered_to_execution": sum(1 for r in repaired if r.get("exec_ok")),
        "repairs_recovered_correct": sum(1 for row in all_rows if (row["record"].get("qm_repair_count") or 0) > 0
                                         and row["correct"]),
        "error_types": dict(errors),
        "optimizer_invoked": sum(1 for r in recs if (r.get("qm_optimizer_rounds") or 0) > 0),
        "optimizer_rewrites_applied": sum(1 for r in recs if r.get("qm_optimization_applied")),
        "optimizer_rewrites_result_equal": sum(1 for r in recs if r.get("qm_optimizer_result_equal") is True),
        "schema_backend": dict(Counter(r.get("qm_schema_backend") for r in recs)),
        "semantic_judge_unavailable": sum(1 for r in recs if any(
            "LLM semantic judge unavailable" in a for a in r.get("qm_assumptions_raw") or [])),
        "llm_calls_distribution": dict(sorted(Counter(r.get("qm_llm_calls") for r in recs).items(),
                                              key=lambda kv: (kv[0] is None, kv[0]))),
        "calls_without_token_usage": sum(r.get("qm_calls_without_usage") or 0 for r in recs),
    }


def consistency(scored: dict, arm: str) -> tuple[int, int] | None:
    runs = [scored[rep][arm] for rep in sorted(scored) if arm in scored[rep]]
    if len(runs) < 2:
        return None
    verdicts = defaultdict(list)
    for run in runs:
        for row in run:
            verdicts[(row["group"], row["id"])].append(row["correct"])
    stable = sum(1 for v in verdicts.values() if len(v) == len(runs) and len(set(v)) == 1)
    return stable, len(verdicts)


def paired(rows_a: list[dict], rows_b: list[dict]) -> dict:
    a = {(r["group"], r["id"]): bool(r["correct"]) for r in rows_a}
    b = {(r["group"], r["id"]): bool(r["correct"]) for r in rows_b}
    keys = a.keys() & b.keys()
    only_a = sum(1 for k in keys if a[k] and not b[k])
    only_b = sum(1 for k in keys if b[k] and not a[k])
    return {"n": len(keys), "querymind_only": only_a, "baseline_only": only_b,
            "p_exact_mcnemar": mcnemar_exact(only_a, only_b)}


def fmt(pair) -> str:
    return pct(*pair) if isinstance(pair, tuple) else "N/A"


def markdown(name: str, scored: dict, summaries: dict, manifest: dict) -> str:
    primary = summaries.get("r1", {})
    arms = [a for a in ARMS if a in primary]
    lines = [f"## {name}", ""]
    header = "| Metric | " + " | ".join(ARM_LABEL[a] for a in arms) + " |"
    lines += [header, "|---|" + "---:|" * len(arms)]

    def row(label, key, render=fmt):
        lines.append(f"| {label} | " + " | ".join(render(primary[a].get(key)) for a in arms) + " |")

    if name == "stakeholder":
        row("Easy accuracy (set easy)", "set_easy")
        row("Hard accuracy (set hard)", "set_hard")
        row("Unanswerable refused + field named", "unanswerable_refused_correctly")
        row("Fabrications on unanswerable (lower is better)", "fabrications")
        row("Ambiguity flagged (assumption stated)", "ambiguity_flagged")
        row("Assumptions stated on unambiguous reference questions", "assumptions_on_reference")
    else:
        row("Execution accuracy, all", "answer_accuracy_reference")
        row("Execution accuracy, single-table", "set_single")
        row("Execution accuracy, multi-table/nested", "set_multi")
    row("Over-refusal (refused an answerable question)", "over_refusal")
    row("Execution success (all questions)", "exec_success")
    row("Execution success when an answer was attempted", "exec_success_when_attempted")
    row("Write attempts in generated SQL", "write_attempts", lambda v: str(v))
    lines.append("| p50 / p95 end-to-end latency (s) | " + " | ".join(
        f"{primary[a]['latency_s']['p50']:.2f} / {primary[a]['latency_s']['p95']:.2f}"
        if primary[a]["latency_s"]["p50"] is not None else "N/A" for a in arms) + " |")
    lines.append("| Questions over 15 s | " + " | ".join(
        f"{primary[a]['latency_s']['over_15s']}/{primary[a]['latency_s']['n']}" for a in arms) + " |")
    lines.append("| LLM calls / question (mean) | " + " | ".join(
        f"{primary[a]['llm_calls_per_question']:.2f}" if primary[a]["llm_calls_per_question"] is not None
        else "N/A" for a in arms) + " |")
    lines.append("| Tokens / question (prompt+completion, mean) | " + " | ".join(
        f"{primary[a]['tokens_per_question']:.0f}" if primary[a]["tokens_per_question"] is not None
        else "N/A" for a in arms) + " |")
    lines.append("| Gateway errors remaining after retries | " + " | ".join(
        str(primary[a]["infra_errors_remaining"]) for a in arms) + " |")
    lines += ["", "Rates are run r1 with 95% Wilson intervals (stakeholder `score.wilson`)."]

    reps = sorted(summaries)
    if len(reps) > 1:
        key = "set_hard" if name == "stakeholder" else "answer_accuracy_reference"
        lines += ["", "### Repeat stability", "",
                  "| Arm | " + " | ".join(f"{r} correct (all kinds)" for r in reps) + " | Same verdict in every run |",
                  "|---|" + "---:|" * (len(reps) + 1)]
        for arm in arms:
            totals = []
            for rep in reps:
                rows = scored[rep].get(arm, [])
                totals.append(f"{sum(1 for r in rows if r['correct'])}/{len(rows)}")
            stable = consistency(scored, arm)
            lines.append(f"| {ARM_LABEL[arm]} | " + " | ".join(totals) + " | "
                         + (f"{stable[0]}/{stable[1]}" if stable else "N/A") + " |")

    pairs = [(a, b) for a, b in PAIRS if a in primary and b in primary]
    if pairs:
        lines += ["", "### Paired comparison on r1 (exact McNemar, all scored questions)", "",
                  "| Pair (A vs B) | Questions | Only A correct | Only B correct | p |",
                  "|---|---:|---:|---:|---:|"]
        for a, b in pairs:
            p = paired(scored["r1"][a], scored["r1"][b])
            lines.append(f"| {a} vs {b} | {p['n']} | {p['querymind_only']} | {p['baseline_only']} "
                         f"| {p['p_exact_mcnemar']:.3f} |")
    lines += ["", "### Per-question verdicts (r1)", "",
              "| Question | Set | Kind | " + " | ".join(arms) + " |", "|---|---|---|" + "---|" * len(arms)]
    by_q: dict = defaultdict(dict)
    meta = {}
    for arm in arms:
        for r in scored["r1"][arm]:
            by_q[(r["group"], r["id"])][arm] = ("PASS" if r["correct"] else "FAIL") + f": {r['verdict'][:70]}"
            meta[(r["group"], r["id"])] = (r["set"], r["kind"])
    for key in sorted(by_q):
        label = key[1] if name == "stakeholder" else f"{key[1]} ({key[0]})"
        lines.append(f"| {label} | {meta[key][0]} | {meta[key][1]} | "
                     + " | ".join(by_q[key].get(a, "—").replace("|", "/") for a in arms) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "summary.json")
    parser.add_argument("--markdown", type=Path, default=RESULTS / "results.md")
    args = parser.parse_args(argv)
    manifest_path = RESULTS / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    report, sections = {"manifest": manifest, "datasets": {}}, []
    for name in ("stakeholder", "spider"):
        if not (RESULTS / name).exists():
            continue
        scored = score_dataset(name)
        summaries = {rep: {arm: summarize(rows, name) for arm, rows in arms.items()} for rep, arms in scored.items()}
        behaviour = {arm: querymind_behaviour([row for rep in scored.values() for row in rep.get(arm, [])])
                     for arm in ("querymind", "querymind-flat")
                     if any(arm in rep for rep in scored.values())}
        r1 = scored.get("r1", {})
        report["datasets"][name] = {
            "summaries": summaries, "querymind_behaviour": behaviour,
            "consistency": {arm: consistency(scored, arm) for arm in ARMS},
            "paired_r1": {f"{a} vs {b}": paired(r1[a], r1[b]) for a, b in PAIRS if a in r1 and b in r1},
        }
        section = markdown(name, scored, summaries, manifest)
        for arm, stats in behaviour.items():
            section += (f"\n\n### {ARM_LABEL[arm]} behaviour (all runs)\n\n```json\n"
                        + json.dumps(stats, indent=2) + "\n```")
        sections.append(section)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    args.markdown.write_text("# Report evaluation results\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    print(args.markdown.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
