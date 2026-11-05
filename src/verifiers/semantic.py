"""Deterministic input checks establishing the semantic verifier contract."""

from typing import TypedDict


class SemanticResult(TypedDict):
    """Semantic decision, including explicit coverage of the starter checker."""

    matches_question: bool
    answerable: bool
    missing_fields: list[str]
    assumptions: list[str]
    reason: str
    status: str


def verify_semantics(question: str, sql: str, schema_context: str) -> SemanticResult:
    """Check nonempty inputs; report that semantic alignment remains unverified.

    Positive booleans permit the starter pipeline to continue. They are input
    checks only; consumers must retain the explicit placeholder status.
    """
    # TODO(feature/verifiers): detect missing fields, assumptions and SQL intent.
    complete = bool(question.strip() and sql.strip() and schema_context.strip())
    return {
        "matches_question": complete,
        "answerable": complete,
        "missing_fields": [],
        "assumptions": [
            "The starter semantic verifier checks input structure only; "
            "alignment between the question and SQL has not been verified."
        ],
        "reason": (
            "Starter input checks passed; semantic alignment is unverified."
            if complete
            else "A question, SQL statement and schema context are required."
        ),
        "status": "placeholder",
    }
