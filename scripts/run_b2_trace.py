"""Run b2 (k samples, strict majority vote on executed results) and append trace records.

b2 is `src/evaluation/b2.py::run_self_consistency`: k independent generations
from the flat schema with the refusal-permitting generator prompt, each run
read-only, and a candidate is selected only when more than half of all k
samples return the same result multiset. No verification, repair, optimizer or
LLM judge is involved, so b2 isolates "sample more and vote" from the agents.

Records use the stakeholder trace format (see `src/evaluation/stakeholder.py`)
so b2 is graded by the same unchanged scorer as b0, b1 and QueryMind.

Sampling uses temperature > 0 (default 0.7): at temperature 0 all k samples are
near-identical and the vote measures nothing. The temperature is written into
every record.
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
from src.evaluation.b2 import run_self_consistency
from src.evaluation.stakeholder import is_provider_error, to_stakeholder_record
from src.llm import MockProvider, OpenAICompatibleProvider, SQLProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def b2_record(question_id: str, question: str, report: dict, provider: SQLProvider, *,
              model: str, provider_name: str, temperature: float, run_tag: str | None) -> dict:
    """Convert one `run_self_consistency` report into a stakeholder-format record."""
    state = report["state"]
    record = to_stakeholder_record(
        question_id, question, state, model=model, provider_name=provider_name,
        prompt_tokens=getattr(provider, "prompt_tokens", None),
        completion_tokens=getattr(provider, "completion_tokens", None),
        calls_without_usage=getattr(provider, "calls_without_usage", None),
        run_tag=run_tag, arm="b2",
    )
    selected = report.get("selected_index")
    # The merged b2 state has no single "executor" step; the selected candidate executed.
    executed = state.get("status") == "success" and selected is not None
    candidates = report.get("candidates") or []
    record.update({
        "prompt_version": f"b2-k{report['samples']}",
        "temperature": temperature,
        "exec_ok": executed,
        "rows": len(state.get("rows") or []) if executed else None,
        "b2_samples": report["samples"],
        "b2_required_votes": report["required_votes"],
        "b2_majority_count": report["majority_count"],
        "b2_selected_index": selected,
        "b2_refusal_consensus": report.get("refusal_consensus_count"),
        "b2_candidate_status": [c.get("status") for c in candidates],
        "b2_candidate_sql": [c.get("sql") or "" for c in candidates],
    })
    # If a gateway failure cost the vote its majority, the outcome is infrastructure,
    # not an abstention: mark it ProviderError so run_report_eval retries it.
    # (The generator wraps provider errors in ValueError, so they surface as "refused".)
    failures = [c.get("error") or c.get("semantic_reason") or "" for c in candidates]
    failures = [text for text in failures if is_provider_error(text)]
    if failures and not executed:
        record.update(refused=False, missing_field=None, error_type="ProviderError", error=failures[0][:500])
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--ids", help="Comma-separated question IDs (default: all)")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--run-tag")
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
        provider = OpenAICompatibleProvider(temperature=args.temperature)
        if isinstance(provider, MockProvider):
            parser.error("Mock provider selected")
        report = run_self_consistency(item["question"], samples=args.samples, db_path=db_path, provider=provider)
        record = b2_record(item["id"], item["question"], report, provider,
                           model=provider._resolve_model().removeprefix("openai/"),
                           provider_name=settings.model.provider, temperature=args.temperature,
                           run_tag=args.run_tag)
        with args.trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(f"[{item['id']}] votes={record['b2_majority_count']}/{args.samples} exec_ok={record['exec_ok']} "
              f"refused={record['refused']} calls={record['qm_llm_calls']} latency={record['latency_ms']}ms",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
