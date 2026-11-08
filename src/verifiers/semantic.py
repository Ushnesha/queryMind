"""Semantic verifier: does the SQL answer the question, and can the schema answer it?

Two layers run in order:

1. Deterministic checks (always): data the question needs but the schema lacks,
   and ranking/aggregation cues in the question that the SQL must reflect.
2. An LLM judge (optional): the same decision made by a model, returning the
   structured JSON contract below. It runs when a provider is supplied or the
   configured model provider is not ``mock``; if it fails, layer 1 stands.

A failure in either layer fails the check. ``answerable=False`` makes the
orchestrator refuse; ``matches_question=False`` makes it repair the SQL.
"""

from __future__ import annotations

from typing import TypedDict

from src.llm import SQLProvider

from .cues import QuestionIntent, SqlFeatures, missing_concepts, parse_intent, parse_schema, parse_sql
from .judge import as_bool, as_str_list, ask_json, dedupe, resolve_judge


class SemanticResult(TypedDict):
    """Semantic decision with the layers that produced it."""

    matches_question: bool
    answerable: bool
    missing_fields: list[str]
    assumptions: list[str]
    reason: str
    status: str


JUDGE_INSTRUCTIONS = """You are QueryMind's semantic verifier for SQLite Text-to-SQL.
Decide whether the candidate SQL correctly answers the user's question using only the database schema below.

Return ONLY one JSON object, with no Markdown and no commentary, using exactly these keys:
{
  "matches_question": true or false,  // false if the SQL computes something other than what was asked
  "answerable": true or false,        // false only if the schema lacks data the question requires
  "missing_fields": [],               // information the question needs that the schema does not contain
  "assumptions": [],                  // interpretation choices the SQL makes (tie handling, date range, NULL handling)
  "reason": ""                        // one sentence explaining the decision
}"""


def _intent_checks(intent: QuestionIntent, sql: SqlFeatures) -> tuple[list[str], list[str]]:
    """Return (problems, confirmed cues) comparing question wording with the SQL."""
    problems: list[str] = []
    confirmed: list[str] = []
    if intent.top_n is not None:
        if sql.limit is None:
            problems.append(f"The question asks for the top {intent.top_n}, but the SQL has no LIMIT.")
        elif sql.limit != intent.top_n:
            problems.append(f"The question asks for the top {intent.top_n}, but the SQL uses LIMIT {sql.limit}.")
        elif not (sql.has_order or sql.has_max or sql.has_min):
            problems.append(f"The SQL limits to {intent.top_n} rows without ORDER BY, so it does not rank them.")
        else:
            confirmed.append(f"top-{intent.top_n} ranking with LIMIT {sql.limit}")
    if intent.wants_count:
        if sql.has_count or sql.has_sum:
            confirmed.append("COUNT aggregation")
        else:
            problems.append("The question asks how many, but the SQL has no COUNT.")
    if intent.wants_average:
        if sql.has_avg or (sql.has_sum and sql.has_division):
            confirmed.append("AVG aggregation")
        else:
            problems.append("The question asks for an average, but the SQL has no AVG.")
    if intent.wants_sum and not intent.wants_count:
        if sql.has_sum:
            confirmed.append("SUM aggregation")
        elif intent.sums_quantity:
            problems.append("The question asks for a total amount, but the SQL has no SUM.")
        elif sql.has_count:
            confirmed.append("COUNT as the total")
        else:
            problems.append("The question asks for a total, but the SQL has no SUM or COUNT.")
    superlative = intent.wants_max or intent.wants_min
    if superlative and intent.top_n is None:
        if not (sql.has_order or sql.has_max or sql.has_min):
            problems.append("The question asks for a highest/lowest value, but the SQL neither orders nor uses MAX/MIN.")
    if superlative and sql.has_order and not (sql.has_max or sql.has_min):
        if intent.wants_max and not intent.wants_min and not sql.order_desc:
            problems.append("The question asks for the highest values, but the SQL sorts ascending.")
        elif intent.wants_min and not intent.wants_max and sql.order_desc:
            problems.append("The question asks for the lowest values, but the SQL sorts descending.")
    return problems, confirmed


def _assumptions(intent: QuestionIntent, sql: SqlFeatures, notes: list[str]) -> list[str]:
    assumptions: list[str] = []
    if intent.top_n is not None and sql.limit is not None and sql.has_order:
        assumptions.append(
            f"Rows tied at position {intent.top_n} are ordered by the ORDER BY clause; "
            "tied rows beyond the limit are left out."
        )
    if intent.wants_average and sql.has_avg:
        assumptions.append("AVG ignores NULL values.")
    for note in notes:
        assumptions.append(f"Schema retrieval note: {note}")
    return assumptions


def deterministic_semantics(question: str, sql: str, schema_context: str) -> SemanticResult:
    """Rule-based semantic decision; never calls a model or opens a database."""
    if not (question.strip() and sql.strip() and schema_context.strip()):
        return {
            "matches_question": False,
            "answerable": False,
            "missing_fields": [],
            "assumptions": [],
            "reason": "A question, SQL statement and schema context are required.",
            "status": "deterministic",
        }
    schema = parse_schema(schema_context)
    intent = parse_intent(question)
    features = parse_sql(sql)
    missing = missing_concepts(question, schema) if schema.tables else []
    if missing:
        return {
            "matches_question": False,
            "answerable": False,
            "missing_fields": missing,
            "assumptions": [],
            "reason": (
                f"The question needs {', '.join(missing)}, which the retrieved schema does not contain."
            ),
            "status": "deterministic",
        }
    problems, confirmed = _intent_checks(intent, features)
    if problems:
        reason = " ".join(problems)
    elif confirmed:
        reason = "SQL reflects the question's " + ", ".join(confirmed) + "."
    else:
        reason = "No ranking or aggregation cues to check; required data is present in the schema."
    return {
        "matches_question": not problems,
        "answerable": True,
        "missing_fields": [],
        "assumptions": _assumptions(intent, features, schema.notes),
        "reason": reason,
        "status": "deterministic",
    }


def judge_semantics(question: str, sql: str, schema_context: str, provider: SQLProvider) -> SemanticResult:
    """Ask an LLM for the structured semantic decision; raises on an unusable reply."""
    instructions = (
        f"{JUDGE_INSTRUCTIONS}\n\nDatabase schema:\n{schema_context.strip()}"
        f"\n\nCandidate SQL:\n{sql.strip()}"
    )
    data = ask_json(provider, question, instructions)
    if "matches_question" not in data or "answerable" not in data:
        raise ValueError("Judge reply is missing matches_question or answerable.")
    answerable = as_bool(data["answerable"], True)
    return {
        "matches_question": as_bool(data["matches_question"], True) and answerable,
        "answerable": answerable,
        "missing_fields": as_str_list(data.get("missing_fields")),
        "assumptions": as_str_list(data.get("assumptions")),
        "reason": str(data.get("reason") or "").strip(),
        "status": "llm",
    }


def verify_semantics(
    question: str,
    sql: str,
    schema_context: str,
    *,
    provider: SQLProvider | None = None,
    use_llm: bool | None = None,
) -> SemanticResult:
    """Decide whether SQL answers the question and whether the schema can answer it.

    ``provider`` supplies the LLM judge explicitly. ``use_llm=False`` forces
    deterministic-only checks; ``None`` uses the judge when the configured model
    provider is not ``mock``.
    """
    rules = deterministic_semantics(question, sql, schema_context)
    if not rules["answerable"]:
        return rules  # already refused (missing inputs or data); no judge call needed
    judge = resolve_judge(provider, use_llm)
    if judge is None:
        return rules
    try:
        llm = judge_semantics(question, sql, schema_context, judge)
    except Exception as exc:
        rules["assumptions"].append(f"LLM semantic judge unavailable ({exc}); deterministic checks only.")
        return rules

    answerable = rules["answerable"] and llm["answerable"]
    matches = rules["matches_question"] and llm["matches_question"]
    if not rules["answerable"] or not rules["matches_question"]:
        reason = rules["reason"]
    elif not llm["answerable"] or not llm["matches_question"]:
        reason = "LLM judge: " + (llm["reason"] or "the SQL does not answer the question.")
    else:
        reason = rules["reason"] + (" LLM judge agrees: " + llm["reason"] if llm["reason"] else "")
    return {
        "matches_question": matches,
        "answerable": answerable,
        "missing_fields": dedupe(rules["missing_fields"] + llm["missing_fields"]),
        "assumptions": dedupe(rules["assumptions"] + llm["assumptions"]),
        "reason": reason,
        "status": "deterministic+llm",
    }


__all__ = ["SemanticResult", "verify_semantics", "deterministic_semantics", "judge_semantics"]
