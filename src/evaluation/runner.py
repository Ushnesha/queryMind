"""Tiny reference-SQL evaluation harness for the repository's demo cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from src.db import execute_sql
from src.evaluation.metrics import summarize_results, summarize_runs
from src.orchestrator import run_querymind
from src.score import results_equal
from src.state import AgentState


def load_questions(path: str | Path) -> list[dict[str, str]]:
    """Read ``questions: [{id, question, sql}]``; reference SQL is optional."""
    with Path(path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    questions = document.get("questions") if isinstance(document, dict) else None
    if not isinstance(questions, list):
        raise ValueError("Evaluation YAML must contain a 'questions' list.")
    result: list[dict[str, str]] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            raise ValueError(f"Evaluation question {index} must contain a string 'question'.")
        record = {"id": str(item.get("id", index)), "question": item["question"]}
        reference = item.get("sql", item.get("reference_sql", item.get("expected_sql")))
        if reference is not None:
            if not isinstance(reference, str):
                raise ValueError(f"Evaluation question {index} has non-string reference SQL.")
            record["sql"] = reference
        result.append(record)
    return result


def run_evaluation(
    questions: Sequence[Mapping[str, str]],
    *,
    db_path: str | Path | None = None,
    run_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run small offline cases and compare output with read-only reference SQL.

    This starter compares exact columns and unordered rows through the shared
    mechanical scorer. It does not evaluate natural-language answer quality.
    """
    cases: list[dict[str, Any]] = []
    states: list[AgentState] = []
    options: dict[str, Any] = {"schema_mode": "flat", **(run_options or {})}
    for index, question in enumerate(questions, start=1):
        state = run_querymind(question["question"], db_path=db_path, **options)
        states.append(state)
        case: dict[str, Any] = {
            "id": question.get("id", str(index)),
            "question": question["question"],
            "correct": None,
            "state": state,
        }
        reference_sql = question.get("sql")
        if reference_sql:
            expected = execute_sql(reference_sql, db_path=db_path)
            case["correct"] = state.get("status") == "success" and results_equal(
                state.get("rows", []),
                state.get("columns", []),
                expected["rows"],
                expected["columns"],
            )
        cases.append(case)
    return {
        "scope": "starter offline reference-SQL smoke evaluation",
        "cases": cases,
        "metrics": {**summarize_runs(states), **summarize_results(cases)},
    }
