"""Text-to-SQL generation and repair adapter around the replaceable provider."""

from __future__ import annotations

from src.llm import SQLProvider, get_provider

SYSTEM_INSTRUCTIONS = (
    "You are QueryMind's Text-to-SQL generation agent for SQLite.\n"
    "Generate a SQLite query that directly answers the user's question based on the provided schema.\n\n"
    "Strict Rules:\n"
    "1. Generate SQLite-compatible SQL only.\n"
    "2. Generate exactly one query statement. It must begin with SELECT or WITH.\n"
    "3. Never generate write operations: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, ATTACH, DETACH, or PRAGMA.\n"
    "4. Use ONLY tables and columns explicitly present in the supplied database schema. Never invent identifiers.\n"
    "5. Use explicit JOIN syntax when combining tables.\n"
    "6. Return ONLY the raw SQL query. Do not wrap in Markdown code fences (```sql ... ```) and do not provide explanations.\n"
    "7. If the question cannot be answered because required information is absent from the schema, return: NOT_ANSWERABLE:<missing field>"
)

REPAIR_INSTRUCTIONS = (
    "--- REPAIR TASK ---\n"
    "The previous query failed verification. Repair the SQL so it passes verification while preserving the user's original intent.\n"
    "Rules:\n"
    "- Preserve the original question's intent.\n"
    "- Fix the exact verification failure.\n"
    "- Use only the supplied schema.\n"
    "- Return exactly one SQLite SELECT or WITH query.\n"
    "- Return raw SQL only with no Markdown fences or commentary."
)


def build_prompt_context(schema_context: str, *, feedback: str | None = None) -> str:
    """Format the schema and generation/repair instructions for the provider."""
    parts = [
        SYSTEM_INSTRUCTIONS,
        f"\nDatabase Schema:\n{schema_context.strip()}",
    ]
    if feedback:
        parts.append(f"\n{REPAIR_INSTRUCTIONS}")
        parts.append(f"\nVerification Feedback:\n{feedback.strip()}")
    return "\n".join(parts)


def normalize_sql(raw_sql: str) -> str:
    """Normalize model output by stripping surrounding whitespace and code fences."""
    if not isinstance(raw_sql, str):
        return ""
    text = raw_sql.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])
    return text.strip()


def generate_sql(
    question: str,
    schema_context: str,
    *,
    provider: SQLProvider | None = None,
    feedback: str | None = None,
) -> str:
    """Generate SQL offline by default; optional feedback is supplied during repair."""
    context = build_prompt_context(schema_context, feedback=feedback)
    raw_sql = (provider or get_provider("mock")).generate(question, context)
    return normalize_sql(raw_sql)
