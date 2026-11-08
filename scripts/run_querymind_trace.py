"""Run QueryMind on a stakeholder-format question file and append trace records.

The output JSONL is read by the stakeholder's unchanged scorer, exactly like
the b0/b1 traces written by `external/agentic-sql-analyst/src/baseline.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from dotenv import load_dotenv

from src.config import load_settings
from src.evaluation.stakeholder import to_stakeholder_record
from src.llm import MockProvider, get_provider
from src.orchestrator import run_querymind

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--ids", help="Comma-separated question IDs (default: all)")
    parser.add_argument("--schema-mode", choices=("flat", "neo4j"))
    parser.add_argument("--run-tag")
    parser.add_argument("--arm-name", default="querymind", help="Arm label written to the trace")
    args = parser.parse_args(argv)

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    settings = load_settings()
    if settings.model.provider == "mock":
        parser.error("config/settings.yaml selects the mock provider; live evaluation needs a real model")
    questions = yaml.safe_load(args.questions.read_text(encoding="utf-8")) or []
    wanted = {item.strip() for item in args.ids.split(",")} if args.ids else None
    db_path = args.db.resolve()
    args.trace.parent.mkdir(parents=True, exist_ok=True)

    for item in questions:
        if wanted is not None and item["id"] not in wanted:
            continue
        provider = get_provider(settings.model.provider)
        if isinstance(provider, MockProvider):
            parser.error("Mock provider selected")
        state = run_querymind(item["question"], schema_mode=args.schema_mode, db_path=db_path,
                              provider=provider, settings=settings)
        model = provider._resolve_model() if hasattr(provider, "_resolve_model") else type(provider).__name__
        record = to_stakeholder_record(
            item["id"], item["question"], state,
            model=model.removeprefix("openai/"), provider_name=settings.model.provider,
            prompt_tokens=getattr(provider, "prompt_tokens", None),
            completion_tokens=getattr(provider, "completion_tokens", None),
            calls_without_usage=getattr(provider, "calls_without_usage", None),
            run_tag=args.run_tag, arm=args.arm_name,
        )
        with args.trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(f"[{item['id']}] status={record['qm_status']} exec_ok={record['exec_ok']} "
              f"refused={record['refused']} calls={record['qm_llm_calls']} "
              f"latency={record['latency_ms']}ms backend={record['qm_schema_backend']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
