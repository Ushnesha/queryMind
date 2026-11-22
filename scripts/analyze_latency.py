"""R6: end-to-end and per-step latency of QueryMind, before vs after the fix.

"Before" defaults to the Milestone 2 stakeholder traces committed in the repo
(17 questions x 3 repeats; total latency only, per-step time was not logged
then). "After" defaults to the 60-question runs, whose records carry
`qm_node_latency_ms` and `qm_node_tokens`. The headline comparison uses only
the question IDs present in both, so the question mix cannot explain the change;
the full "after" set is reported too.

    python -m scripts.analyze_latency
    python -m scripts.analyze_latency --after "eval/results/report/stakeholder60/r*/querymind__main.jsonl"

Writes eval/results/latency/latency_summary.json and latency.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import statistics
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BEFORE = "eval/results/report/stakeholder/r*/querymind__main.jsonl"
DEFAULT_AFTER = "eval/results/report/stakeholder60/r*/querymind__main.jsonl"
OUT_DIR = PROJECT_ROOT / "eval/results/latency"
TARGET_P50_ANSWERED_S = 15.0
# Display order of agent steps (pipeline order).
NODE_ORDER = ("schema_retriever", "sql_generator", "safety_verifier", "syntax_verifier", "semantic_verifier",
              "optimizer", "executor", "result_verifier", "response_generator")


def load_records(pattern: str) -> list[dict]:
    paths = sorted(glob.glob(str(PROJECT_ROOT / pattern) if not Path(pattern).is_absolute() else pattern))
    return [json.loads(line) for path in paths
            for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def nearest_rank(values: list[float], q: float) -> float | None:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else None


def summarize(records: list[dict]) -> dict:
    """Latency (s) and per-step cost over stakeholder-format QueryMind records."""
    timed = [r for r in records if isinstance(r.get("latency_ms"), (int, float))]
    total = [r["latency_ms"] / 1000 for r in timed]
    answered = [r["latency_ms"] / 1000 for r in timed if r.get("exec_ok")]
    with_nodes = [r for r in timed if isinstance(r.get("qm_node_latency_ms"), dict)]
    nodes = sorted({n for r in with_nodes for n in r["qm_node_latency_ms"]},
                   key=lambda n: (NODE_ORDER.index(n) if n in NODE_ORDER else len(NODE_ORDER), n))
    per_node = {}
    for node in nodes:
        ms = [float(r["qm_node_latency_ms"].get(node, 0.0)) for r in with_nodes]
        tokens = [(r.get("qm_node_tokens") or {}).get(node) or {} for r in with_nodes]
        per_node[node] = {
            "mean_s": statistics.fmean(ms) / 1000,
            "share_of_total": sum(ms) / sum(r["latency_ms"] for r in with_nodes) if with_nodes else None,
            "mean_llm_calls": statistics.fmean(t.get("llm_calls", 0) for t in tokens),
            "mean_completion_tokens": statistics.fmean(t.get("completion_tokens", 0) for t in tokens),
            "mean_prompt_tokens": statistics.fmean(t.get("prompt_tokens", 0) for t in tokens),
        }
    completion = [r["completion_tokens"] for r in timed if isinstance(r.get("completion_tokens"), int)]
    return {
        "records": len(timed),
        "questions": len({r.get("question_id") for r in timed}),
        "mean_s": statistics.fmean(total) if total else None,
        "p50_s": statistics.median(total) if total else None,
        "p95_s": nearest_rank(total, 0.95),
        "answered": len(answered),
        "p50_answered_s": statistics.median(answered) if answered else None,
        "p95_answered_s": nearest_rank(answered, 0.95),
        "over_15s": sum(1 for x in total if x > 15),
        "mean_completion_tokens": statistics.fmean(completion) if completion else None,
        "records_with_node_timing": len(with_nodes),
        "per_node": per_node,
        "slowest": [{"question_id": r.get("question_id"), "latency_s": r["latency_ms"] / 1000,
                     "rows": r.get("rows"), "completion_tokens": r.get("completion_tokens")}
                    for r in sorted(timed, key=lambda r: -r["latency_ms"])[:5]],
    }


def compare(before: list[dict], after: list[dict]) -> dict:
    shared = {r.get("question_id") for r in before} & {r.get("question_id") for r in after}
    result = {
        "before": summarize(before),
        "after_same_questions": summarize([r for r in after if r.get("question_id") in shared]),
        "after_all": summarize(after),
        # Answered runs only: every step ran, so per-step bars are comparable (figure).
        "before_answered": summarize([r for r in before if r.get("exec_ok")]),
        "after_answered": summarize([r for r in after if r.get("exec_ok")]),
        "shared_question_ids": sorted(shared),
        "target_p50_answered_s": TARGET_P50_ANSWERED_S,
    }
    p50 = result["after_all"]["p50_answered_s"]
    result["target_met"] = None if p50 is None else p50 < TARGET_P50_ANSWERED_S
    return result


def markdown(result: dict, before_label: str, after_label: str) -> str:
    def s(value):
        return "N/A" if value is None else f"{value:.1f}"

    cols = (("before", f"Before ({before_label})"), ("after_same_questions", "After, same questions"),
            ("after_all", f"After, all ({after_label})"))
    lines = ["# R6 latency: before vs after", "",
             "| Metric | " + " | ".join(label for _, label in cols) + " |", "|---|" + "---:|" * len(cols)]
    for key, label in (("records", "Runs"), ("questions", "Questions"), ("p50_s", "p50, all runs (s)"),
                       ("p95_s", "p95, all runs (s)"), ("p50_answered_s", "p50, answered (s)"),
                       ("p95_answered_s", "p95, answered (s)"), ("over_15s", "Runs over 15 s"),
                       ("mean_completion_tokens", "Completion tokens / run")):
        values = [result[c][key] for c, _ in cols]
        lines.append(f"| {label} | " + " | ".join(
            str(v) if isinstance(v, int) else s(v) for v in values) + " |")
    met = result["target_met"]
    lines += ["", f"Target: p50 latency on answered questions < {TARGET_P50_ANSWERED_S:.0f} s -> "
              + ("**met**" if met else "**not met**" if met is False else "no 'after' data yet"), ""]
    per_node = result["after_all"]["per_node"]
    if per_node:
        lines += ["## Time and tokens per agent step (after, mean per run)", "",
                  "| Step | Mean time (s) | Share of total | LLM calls | Prompt tokens | Completion tokens |",
                  "|---|---:|---:|---:|---:|---:|"]
        for node, item in per_node.items():
            lines.append(f"| {node} | {item['mean_s']:.2f} | {100 * (item['share_of_total'] or 0):.0f}% | "
                         f"{item['mean_llm_calls']:.2f} | {item['mean_prompt_tokens']:.0f} | "
                         f"{item['mean_completion_tokens']:.0f} |")
    else:
        lines.append("Per-step timing: no 'after' records with `qm_node_latency_ms` yet.")
    if not result["before"]["per_node"]:
        lines += ["", "Milestone 2 traces logged only end-to-end latency, so 'before' has no per-step split."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", default=DEFAULT_BEFORE, help="Glob of 'before' trace files")
    parser.add_argument("--after", default=DEFAULT_AFTER, help="Glob of 'after' trace files")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--questions", type=Path, default=None,
                        help="Question file whose IDs the 'after' records are limited to (default: "
                             "eval/questions_60.yaml with the default --after), like the stakeholder scorer")
    args = parser.parse_args(argv)
    before, after = load_records(args.before), load_records(args.after)
    questions = args.questions or (PROJECT_ROOT / "eval/questions_60.yaml" if args.after == DEFAULT_AFTER else None)
    if questions is not None:
        import yaml

        # Traces keep records of questions later dropped from the set (e.g. a removed duplicate).
        wanted = {item["id"] for item in yaml.safe_load(questions.read_text(encoding="utf-8")) or []}
        after = [r for r in after if r.get("question_id") in wanted]
    if not before:
        parser.error(f"No 'before' records match {args.before}")
    result = compare(before, after)
    result["sources"] = {"before": args.before, "after": args.after}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "latency_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    text = markdown(result, "Milestone 2" if args.before == DEFAULT_BEFORE else "before",
                    f"{result['after_all']['questions']}-question set" if args.after == DEFAULT_AFTER else "after")
    (args.out / "latency.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
