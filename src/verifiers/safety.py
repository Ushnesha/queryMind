"""Read-only policy checks shared with the execution boundary."""

from typing import TypedDict

from src.db import validate_readonly


class CheckResult(TypedDict):
    """Public syntax/safety check result."""

    ok: bool
    error: str | None


def check_safety(sql: str) -> CheckResult:
    """Check the common SQL read-only guard without opening a database.

    Execution always enforces its own read-only connection and guard, even
    when this optional verification node is disabled for ablation.
    """
    try:
        validate_readonly(sql)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": None}
