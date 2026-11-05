"""Node switches and single-question smoke runs for future ablation work."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.evaluation.metrics import summarize_runs
from src.orchestrator import run_querymind


def ablation_variants() -> dict[str, dict[str, bool]]:
    """Return independent node toggles; executor read-only safety stays active."""
    enabled = {
        "enable_syntax": True,
        "enable_semantic": True,
        "enable_optimizer": True,
        "enable_result_verifier": True,
    }
    variants = {"all_enabled": dict(enabled)}
    for flag in enabled:
        variants[f"without_{flag.removeprefix('enable_')}"] = {**enabled, flag: False}
    return variants


def run_ablation(question: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    """Smoke-test each switch on one question; no experiment conclusions yet."""
    # TODO(feature/eval-ui): add controlled multi-question ablation experiments.
    variants: dict[str, Any] = {}
    for name, flags in ablation_variants().items():
        state = run_querymind(question, schema_mode="flat", db_path=db_path, **flags)
        variants[name] = {"flags": flags, "state": state}
    return {
        "scope": "single-question ablation switch smoke test; not a completed experiment",
        "question": question,
        "variants": variants,
        "metrics": summarize_runs(item["state"] for item in variants.values()),
    }
