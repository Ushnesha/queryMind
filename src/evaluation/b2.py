"""Reserved interface for Developer 5's later self-consistency experiment."""

from __future__ import annotations

from typing import Any


def run_self_consistency(question: str, *, samples: int = 3) -> dict[str, Any]:
    """Return an explicit unimplemented status without fabricating results."""
    if samples < 1:
        raise ValueError("samples must be positive")
    # TODO(feature/eval-ui): implement b2 sampling, selection, and comparison.
    return {
        "implemented": False,
        "question": question,
        "samples": samples,
        "reason": "Self-consistency is reserved for feature/eval-ui.",
    }
