"""Reference-result evaluation and replay for the preliminary Milestone 2 study."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from src.config import load_settings
from src.db import execute_sql
from src.evaluation.metrics import summarize_results, summarize_runs
from src.llm import MockProvider, SQLProvider, get_provider
from src.orchestrator import run_querymind
from src.score import results_equal
from src.state import AgentState


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load questions and retain annotations used for stratification and subsets.

    Reference SQL is optional; a case without a reference or answerability label
    is unscored. Unknown metadata is retained so experimental annotations do not
    silently disappear at the YAML boundary.
    """
    with Path(path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    questions = document.get("questions") if isinstance(document, dict) else None
    if not isinstance(questions, list):
        raise ValueError("Evaluation YAML must contain a 'questions' list.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError(f"Evaluation question {index} must contain a nonempty string 'question'.")
        identifier = str(item.get("id", index)).strip()
        if not identifier or identifier in seen:
            raise ValueError(f"Evaluation question {index} has a blank or duplicate id: {identifier!r}.")
        seen.add(identifier)
        record = {**item, "id": identifier, "question": item["question"].strip()}
        reference = item.get("sql", item.get("reference_sql", item.get("expected_sql")))
        if reference is not None:
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError(f"Evaluation question {identifier} has invalid reference SQL.")
            record["sql"] = reference
        for key in ("answerable", "ambiguous"):
            if key in item and not isinstance(item[key], bool):
                raise ValueError(f"Evaluation question {identifier}: {key} must be a boolean.")
        if "difficulty" in item and item["difficulty"] not in {"easy", "hard"}:
            raise ValueError(f"Evaluation question {identifier}: difficulty must be easy or hard.")
        for key in ("missing_fields", "expected_tables", "expected_join_paths", "tags"):
            if key in item and (
                not isinstance(item[key], list)
                or not all(isinstance(value, str) and value.strip() for value in item[key])
            ):
                raise ValueError(f"Evaluation question {identifier}: {key} must be a list of nonempty strings.")
        result.append(record)
    return result


class _CountedProvider:
    """Count generation attempts without claiming every attempt is an API call."""

    def __init__(self, provider: SQLProvider) -> None:
        self.provider = provider
        self.calls = 0
        self.model_calls_before = _model_counter(provider)

    def generate(self, question: str, schema_context: str) -> str:
        self.calls += 1
        return self.provider.generate(question, schema_context)


def run_evaluation(
    questions: Sequence[Mapping[str, Any]],
    *,
    db_path: str | Path | None = None,
    run_options: Mapping[str, Any] | None = None,
    arm: str = "querymind",
    samples: int = 3,
    provider: SQLProvider | None = None,
) -> dict[str, Any]:
    """Execute an arm and score cases with the shared result-multiset scorer.

    ``b2`` is an alias for the reduced preliminary ``b2-small`` arm. Reference
    execution is outside the measured inference latency. Each failure remains
    visible as its own case instead of aborting or shrinking the denominator.
    """
    if arm not in {"b1", "b2", "b2-small", "querymind"}:
        raise ValueError("arm must be b1, b2, b2-small, or querymind")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 1:
        raise ValueError("samples must be a positive integer")
    arm = "b2-small" if arm == "b2" else arm
    options = {"schema_mode": "flat", **(run_options or {})}
    if "db_path" in options:
        raise ValueError("Pass db_path directly, not in run_options.")
    configured_provider = options.pop("provider", None)
    if provider is not None and configured_provider is not None:
        raise ValueError("Pass provider directly or in run_options, not both.")
    selected_provider = provider if provider is not None else configured_provider
    records: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        started = perf_counter()
        counted: _CountedProvider | None = None
        actual_provider = selected_provider
        try:
            if actual_provider is None:
                settings = options.get("settings") or load_settings()
                actual_provider = get_provider(settings.model.provider)
            if arm == "querymind":
                counted = _CountedProvider(actual_provider)
                state = run_querymind(question["question"], db_path=db_path, provider=counted, **options)
                metrics = state.setdefault("metrics", {})
                metrics.setdefault("generation_calls", counted.calls)
                after = _model_counter(actual_provider)
                before = counted.model_calls_before
                metrics.setdefault("llm_calls", max(0, after - before) if before is not None and after is not None else None)
                metrics.setdefault("provider", type(actual_provider).__name__)
            elif arm == "b1":
                from src.evaluation.b2 import run_single_generation

                state = run_single_generation(question["question"], db_path=db_path, provider=actual_provider)
            else:
                from src.evaluation.b2 import run_self_consistency

                experiment = run_self_consistency(
                    question["question"], samples=samples, db_path=db_path, provider=actual_provider
                )
                state = experiment["state"]
                # Preserve every candidate and the voting evidence in JSONL replay.
                state["metrics"]["self_consistency"] = {
                    key: value for key, value in experiment.items() if key != "state"
                }
        except Exception as exc:
            state = {
                "question": question["question"], "status": "error", "error": str(exc),
                "answerable": True, "rows": [], "columns": [], "trace": [],
                "metrics": {
                    "total_latency_ms": (perf_counter() - started) * 1000,
                    "generation_calls": counted.calls if counted is not None else 0,
                    "llm_calls": 0 if isinstance(actual_provider, MockProvider) else None,
                },
            }
        state.setdefault("metrics", {}).setdefault("total_latency_ms", (perf_counter() - started) * 1000)
        if actual_provider is not None:
            state["metrics"].setdefault("provider", type(actual_provider).__name__)
        records.append({"question_id": str(question.get("id", index)), "state": state})
    report = score_records(questions, records, db_path=db_path, arm=arm)
    if arm == "b2-small":
        report.update(samples=samples, label=f"b2-small preliminary experiment (k={samples})")
    return report


def score_records(
    questions: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    *,
    db_path: str | Path | None = None,
    arm: str = "querymind",
) -> dict[str, Any]:
    """Score saved states without calling a model or rerunning the pipeline.

    Wrapped records match by ``question_id``/``id``. Raw states are positional;
    mixing those two forms or supplying duplicate IDs is rejected. Missing
    records are visible but unscored, never silently omitted questions.
    """
    indexed: dict[str, Mapping[str, Any]] = {}
    positional: list[Mapping[str, Any]] = []
    for record in records:
        identifier = record.get("question_id", record.get("id"))
        if identifier is None:
            positional.append(record)
        else:
            key = str(identifier)
            if key in indexed:
                raise ValueError(f"Duplicate trace question id: {key}")
            indexed[key] = record
    if indexed and positional:
        raise ValueError("Trace records must all carry IDs or all use positional order.")
    question_ids = {str(question.get("id", index)) for index, question in enumerate(questions, start=1)}
    unknown = set(indexed) - question_ids
    if unknown:
        raise ValueError("Trace contains unknown question IDs: " + ", ".join(sorted(unknown)))
    if len(positional) > len(questions):
        raise ValueError("More positional trace records than questions.")
    cases: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        identifier = str(question.get("id", index))
        record = indexed.get(identifier) if indexed else (positional[index - 1] if index <= len(positional) else None)
        if record is None:
            state: AgentState = {
                "question": question["question"], "status": "error", "error": "Missing trace record.",
                "rows": [], "columns": [], "trace": [], "metrics": {},
            }
        else:
            payload = record.get("state", record)
            if not isinstance(payload, Mapping):
                raise ValueError(f"Trace state for {identifier} must be a mapping.")
            state = dict(payload)
        case = _score_case(
            question, state, identifier=identifier, arm=arm, db_path=db_path, missing_trace=record is None
        )
        if record is not None and "provenance" in record:
            case["provenance"] = record["provenance"]
        cases.append(case)
    states = [case["state"] for case in cases]
    placeholders = sorted({
        event.get("node", "unknown") for state in states for event in state.get("trace", [])
        if event.get("status") in {"placeholder", "fallback"}
    })
    providers = sorted({
        str(state.get("metrics", {}).get("provider")) for state in states
        if state.get("metrics", {}).get("provider") is not None
    })
    return {
        "scope": "Milestone 2 preliminary reference-result evaluation; no natural-language answer-quality judging",
        "arm": arm,
        "case_count": len(cases),
        "providers": providers,
        "placeholder_components": placeholders,
        "limitations": sorted({
            str(question["reference_assumption"]) for question in questions if question.get("reference_assumption")
        }),
        "cases": cases,
        "metrics": {**summarize_runs(states), **summarize_results(cases)},
        "scoring": {
            "results": "Shared scorer: exact column labels and unordered row multisets, including duplicate counts; no numeric tolerance.",
            "unanswerable": "Correct only for an informed refusal matching annotated missing fields; generic unsupported-provider refusals do not count.",
            "latency": "Inference latency excludes reference SQL execution and scoring.",
            "calls": "Generation attempts are separate from instrumented LLM calls; unknown LLM counts remain null.",
        },
    }


def _score_case(
    question: Mapping[str, Any], state: AgentState, *, identifier: str, arm: str, db_path: str | Path | None,
    missing_trace: bool = False,
) -> dict[str, Any]:
    refused = state.get("status") == "refused"
    actual_missing = list(state.get("missing_fields") or [])
    expected_missing = question.get("missing_fields", [])
    informed_refusal = refused and bool(actual_missing) and any(
        _same_field(actual, expected) for actual in actual_missing for expected in expected_missing
    )
    trace = state.get("trace", [])
    ambiguity_flagged = bool(state.get("ambiguity_flagged")) or any(
        bool(event.get("ambiguity_flagged")) for event in trace
    )
    # Assumptions are only ambiguity evidence if actually recorded by a completed
    # semantic verifier, rather than the starter's generic unverified disclaimer.
    semantic_completed = any(
        event.get("node") == "semantic_verifier" and event.get("status") in {"pass", "warning"}
        for event in trace
    )
    ambiguity_flagged = ambiguity_flagged or bool(semantic_completed and state.get("assumptions"))
    metrics = state.get("metrics", {})
    case: dict[str, Any] = {
        "id": identifier, "question_id": identifier, "question": question["question"],
        "arm": arm, "correct": None, "state": state, "refused": refused,
        "missing_fields": actual_missing, "missing_field": actual_missing[0] if actual_missing else None,
        "informed_refusal": informed_refusal, "ambiguity_flagged": ambiguity_flagged,
        "llm_calls": metrics.get("llm_calls"), "generation_calls": metrics.get("generation_calls"),
        "latency_ms": metrics.get("total_latency_ms"),
    }
    for key in ("difficulty", "answerable", "ambiguous", "tags", "expected_tables", "expected_join_paths", "reference_assumption"):
        if key in question:
            case[key] = question[key]
    if missing_trace:
        case["unscored_reason"] = "Missing trace record."
    elif question.get("answerable") is False:
        case["correct"] = informed_refusal
    else:
        reference = question.get("sql", question.get("reference_sql", question.get("expected_sql")))
        if reference:
            try:
                expected = execute_sql(reference, db_path=db_path)
                case["correct"] = state.get("status") == "success" and results_equal(
                    state.get("rows", []), state.get("columns", []), expected["rows"], expected["columns"]
                )
            except Exception as exc:
                case["reference_error"] = str(exc)
    return case


def _same_field(actual: Any, expected: Any) -> bool:
    """Allow schema labels such as 'cost' and 'product cost' to refer to a field."""
    left = " ".join(str(actual).lower().replace("_", " ").split())
    right = " ".join(str(expected).lower().replace("_", " ").split())
    return bool(left and right and (left == right or f" {left} " in f" {right} " or f" {right} " in f" {left} "))


def _model_counter(provider: SQLProvider) -> int | None:
    if isinstance(provider, MockProvider) or getattr(provider, "is_mock", False) is True:
        return 0
    value = getattr(provider, "llm_calls", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
