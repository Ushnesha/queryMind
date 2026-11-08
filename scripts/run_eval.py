"""Evaluate arms, replay traces, or compare schema retrieval for Milestone 2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Support both python -m scripts.run_eval and python scripts/run_eval.py.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROJECT_ROOT
from src.evaluation import load_questions, run_evaluation
from src.evaluation.ablation import run_schema_comparison
from src.evaluation.runner import score_records


METRIC_ROWS = (
    ("Accuracy", "result_accuracy", True),
    ("Scored cases", "scored_cases", False),
    ("Unscored cases", "unscored_cases", False),
    ("Reference errors", "reference_error_count", False),
    ("Easy accuracy", "easy_accuracy", True),
    ("Hard accuracy", "hard_accuracy", True),
    ("Completion", "completion_rate", True),
    ("Execution success", "execution_success_rate", True),
    ("Informed unanswerable refusal", "unanswerable_refusal_rate", True),
    ("Raw unanswerable refusal", "raw_unanswerable_refusal_rate", True),
    ("Fabrication proxy", "fabrication_rate", True),
    ("Ambiguity flagged", "ambiguity_flagged_rate", True),
    ("Over-refusal", "over_refusal_rate", True),
    ("LLM calls/question", "llm_calls_per_question", False),
    ("Generations/question", "generation_calls_per_question", False),
    ("p50 latency (ms)", "p50_latency_ms", False),
    ("p95 latency (ms)", "p95_latency_ms", False),
)


def select_questions(questions: list[dict], subset: str, limit: int | None = None) -> list[dict]:
    if limit is not None and limit < 1:
        raise ValueError("--limit must be positive")
    selected = questions if subset == "all" else [q for q in questions if subset in q.get("tags", [])]
    # Old two-question fixtures remain runnable without adding metadata.
    if not selected and subset != "all" and not any(q.get("tags") for q in questions):
        selected = questions[: {"b2": 7, "ablation": 10, "schema": 10}[subset]]
    if not selected:
        raise ValueError(f"No questions selected for subset {subset!r}")
    return selected[:limit] if limit else selected


def _display(value: Any, percent: bool = False) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%" if percent else f"{value:.3f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(report: dict[str, Any]) -> str:
    """Build reviewable tables from recorded measurements only."""
    lines = ["# QueryMind Milestone 2 preliminary evaluation", "", str(report.get("scope", "")), "",
             "These are recorded local measurements. N/A means no labelled cases or no instrumentation.", ""]
    if "comparison" in report and isinstance(report["comparison"], dict):
        arms = report["comparison"]
        lines.extend(["## Paired arm comparison", "", "All arms use the same question IDs. b2 is reduced preliminary self-consistency, not the final k=5 configuration.", ""])
    elif "metrics" in report:
        arms = {report.get("arm", "querymind"): report}
    else:
        arms = report.get("variants", {})
    if arms:
        lines.extend(["| Metric | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)])
        lines.append("| Questions | " + " | ".join(str(arm.get("metrics", {}).get("case_count", 1 if arm.get("question") else 0)) for arm in arms.values()) + " |")
        for title, key, percent in METRIC_ROWS:
            lines.append("| " + title + " | " + " | ".join(_display(arm.get("metrics", {}).get(key), percent) for arm in arms.values()) + " |")
        for name, arm in arms.items():
            notes = arm.get("limitations", [])
            if notes:
                lines.extend(["", f"**{name}:** " + " ".join(notes)])
            if arm.get("providers"):
                lines.extend(["", f"**{name} providers:** " + ", ".join(arm["providers"])])
            if arm.get("placeholder_components"):
                lines.extend(["", f"**{name} placeholders/fallbacks:** " + ", ".join(arm["placeholder_components"])])
        if "comparison" in report:
            lines.extend(["", "Question IDs: " + ", ".join(str(c["id"]) for c in next(iter(arms.values())).get("cases", [])), ""])
    if "full_evaluation" in report:
        lines.extend(["", "## Full preliminary fixture (b2 excluded)", ""])
        for name, arm in report["full_evaluation"].items():
            metrics = arm["metrics"]
            lines.append(f"- {name}: {metrics['correct_cases']}/{metrics['scored_cases']} correct; accuracy {_display(metrics['result_accuracy'], True)}.")
    if "variants" in report and isinstance(report.get("comparison"), list):
        lines.extend(["", "## Schema retrieval comparison", "", "| Metric | Flat | Neo4j |", "|---|---:|---:|"])
        for row in report["comparison"]:
            lines.append("| " + " | ".join(_display(row.get(k)) for k in ("metric", "flat", "neo4j")) + " |")
    lines.extend(["", "## Interpretation", "",
                  "Mock generations do not call an LLM and are deterministic; repeated agreement does not establish a self-consistency benefit. "
                  "Deterministic semantic checks are limited to their implemented rules; flat fallback does not validate Neo4j retrieval. "
                  "A successful answer to a labelled unanswerable question is the fabrication proxy; generic unsupported-question refusals are not informed missing-field refusals. "
                  "Accuracy uses exact column labels and unordered row multisets from the shared scorer. Ambiguous references document one interpretation. "
                  "Latency is a single local observation per question, not a repeated model benchmark.", ""])
    return "\n".join(lines)


def _records(report: dict[str, Any]) -> list[dict[str, Any]]:
    if "cases" in report:
        return report["cases"]
    if "state" in report:
        state = report["state"]
        return [{"id": "single_question", "question_id": "single_question", "arm": "querymind",
                 "question": state.get("question", ""), "state": state}]
    result: list[dict[str, Any]] = []
    for group in ("comparison", "full_evaluation", "variants"):
        children = report.get(group, {})
        if isinstance(children, dict):
            for name, child in children.items():
                for case in _records(child):
                    result.append({**case, "configuration": name, "experiment": group})
    return result


def write_artifacts(report: dict[str, Any], output: Path, *, jsonl: Path | None = None, markdown: Path | None = None) -> None:
    # Serialise completely before touching output files. Never emit NaN JSON.
    document = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    records = "".join(json.dumps(case, ensure_ascii=False, allow_nan=False) + "\n" for case in _records(report))
    trace_path = jsonl or output.with_suffix(".jsonl")
    destinations = [output.resolve(), trace_path.resolve()]
    if markdown:
        destinations.append(markdown.resolve())
    if len(set(destinations)) != len(destinations):
        raise ValueError("Report, JSONL and Markdown destinations must be different files")
    for path, text in ((output, document), (trace_path, records)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_report(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("b1", "b2", "b2-small", "querymind", "all"), default="querymind")
    parser.add_argument("--questions", type=Path, default=PROJECT_ROOT / "eval/milestone2.yaml")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--schema-mode", choices=("flat", "neo4j"), default="flat")
    parser.add_argument("--subset", choices=("all", "b2", "ablation", "schema"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--schema-comparison", action="store_true")
    parser.add_argument("--traces", type=Path, help="Score saved JSONL states/cases without generation")
    parser.add_argument("--trace-experiment", choices=("comparison", "full_evaluation", "variants"), help="Select a group from combined report JSONL")
    parser.add_argument("--trace-configuration", help="Select a configuration from combined report JSONL")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    try:
        if args.samples < 1:
            raise ValueError("--samples must be positive")
        if args.traces and (args.arm == "all" or args.schema_comparison):
            raise ValueError("Trace replay requires one arm and cannot run a schema comparison")
        questions = load_questions(args.questions)
        default_subset = "schema" if args.schema_comparison else "b2" if args.arm in {"b2", "b2-small", "all"} else "all"
        if args.traces and args.trace_experiment == "comparison":
            default_subset = "b2"
        elif args.traces and args.trace_experiment == "variants":
            default_subset = "schema" if args.trace_configuration in {"flat", "neo4j"} else "ablation"
        subset = args.subset or default_subset
        selected = select_questions(questions, subset, args.limit)
        if not args.traces and args.arm in {"b2", "b2-small", "all"} and len(selected) > 10:
            raise ValueError("Preliminary b2 is limited to 10 questions; use --subset b2 or --limit 10")
        options = {"schema_mode": args.schema_mode}
        if args.traces:
            records = [json.loads(line) for line in args.traces.read_text(encoding="utf-8").splitlines() if line.strip()]
            if any(not isinstance(record, dict) for record in records):
                raise ValueError("Each JSONL trace line must be an object")
            # A combined artifact holds multiple runs of the same question IDs.
            # Require a group selector before matching IDs, never combine them.
            records = [r for r in records if r.get("arm", args.arm) in {args.arm, "b2-small" if args.arm == "b2" else args.arm}]
            if args.trace_experiment:
                records = [r for r in records if r.get("experiment") == args.trace_experiment]
            if args.trace_configuration:
                records = [r for r in records if r.get("configuration") == args.trace_configuration]
            for field, option in (("experiment", "--trace-experiment"), ("configuration", "--trace-configuration")):
                groups = {r.get(field) for r in records if r.get(field) is not None}
                if len(groups) > 1:
                    raise ValueError(f"Trace file has multiple {field} groups; select one with {option}")
            if not records:
                raise ValueError("No trace records match the selected arm/group")
            if args.subset or args.limit:
                selected_ids = {str(q["id"]) for q in selected}
                records = [r for r in records if r.get("question_id", r.get("id")) is None or str(r.get("question_id", r.get("id"))) in selected_ids]
            report = score_records(selected, records, db_path=args.db_path, arm=args.arm)
        elif args.schema_comparison:
            report = run_schema_comparison(selected, db_path=args.db_path)
        elif args.arm == "all":
            report = {
                "scope": f"Preliminary paired comparison; b2-small k={args.samples}; deterministic mock unless a provider is configured.",
                "comparison": {arm: run_evaluation(selected, arm=arm, db_path=args.db_path, run_options=options, samples=args.samples) for arm in ("b1", "b2-small", "querymind")},
                "full_evaluation": {arm: run_evaluation(select_questions(questions, "all", args.limit), arm=arm, db_path=args.db_path, run_options=options) for arm in ("b1", "querymind")},
            }
        else:
            report = run_evaluation(selected, arm=args.arm, db_path=args.db_path, run_options=options, samples=args.samples)
        output = args.output or PROJECT_ROOT / f"eval/results/{'schema' if args.schema_comparison else args.arm}.json"
        write_artifacts(report, output, jsonl=args.jsonl, markdown=args.markdown)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(render_report(report))
    print(f"Saved report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
