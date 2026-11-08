"""Optional LLM judgement used by the semantic and result verifiers.

The judge only runs when a provider is passed in, or when the configured model
provider is not ``mock``. Any failure is reported back to the caller, which then
keeps its deterministic decision, so verification never depends on the network.
"""

from __future__ import annotations

import json
from typing import Any

from src.llm import SQLProvider, get_provider


def resolve_judge(provider: SQLProvider | None, use_llm: bool | None) -> SQLProvider | None:
    """Pick the LLM to ask, or None for deterministic-only verification."""
    if use_llm is False:
        return None
    if provider is not None:
        return provider
    try:
        from src.config import load_settings

        name = load_settings().model.provider
    except Exception:
        return None
    if name.lower().strip() == "mock":
        return get_provider("openai") if use_llm else None
    return get_provider(name)


def ask_json(provider: SQLProvider, question: str, instructions: str) -> dict[str, Any]:
    """Send a prompt through the SQL provider interface and parse a JSON object reply."""
    raw = provider.generate(question, instructions)
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"Judge did not return a JSON object: {text[:200]!r}")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Judge reply must be a JSON object.")
    return data


def as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return default


def as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            output.append(item.strip())
    return output
