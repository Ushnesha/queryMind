"""JSON/JSONL trace helpers shared by the starter and future graph nodes."""

import json
from pathlib import Path
from typing import Any

from src.state import AgentState


def add_trace(
    state: AgentState,
    node: str,
    status: str,
    latency_ms: float,
    reason: str = "",
    *,
    iteration: int | None = None,
) -> None:
    """Append one serializable node event to a run."""
    event: dict[str, Any] = {
        "node": node,
        "status": status,
        "latency_ms": round(latency_ms, 3),
        "reason": reason,
    }
    if iteration is not None:
        event["iteration"] = iteration
    json.dumps(event, allow_nan=False)
    state.setdefault("trace", []).append(event)


def write_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append a complete run as one JSON line; never serialize runtime objects."""
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
