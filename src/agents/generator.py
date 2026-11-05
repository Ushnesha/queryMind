"""Thin adapter around the replaceable SQL provider."""

from src.llm import SQLProvider, get_provider


def generate_sql(
    question: str,
    schema_context: str,
    *,
    provider: SQLProvider | None = None,
    feedback: str | None = None,
) -> str:
    """Generate SQL offline by default; optional feedback is supplied during repair."""
    context = schema_context
    if feedback:
        context += "\nPrevious SQL failed verification: " + feedback
    return (provider or get_provider("mock")).generate(question, context)
