"""Compare flat/graph contexts on fixed Spider joins; generation is opt-in."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, resolve_path
from src.schema.spider_cases import load_cases, select_spider_cases
from src.schema.spider_experiment import render_markdown, run_schema_experiment, write_report


def _tokenizer(encoding_name: str | None) -> Callable[[str], int] | None:
    if encoding_name is None:
        return None
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError("An explicit tokenizer requires installing tiktoken.") from exc
    encoding = tiktoken.get_encoding(encoding_name)

    def count(text: str) -> int:
        return len(encoding.encode(text, disallowed_special=()))

    count.tokenizer_name = f"tiktoken:{encoding_name}"  # type: ignore[attr-defined]
    return count


def _provider(factory_path: str | None, model: str | None, temperature: float) -> tuple[Any, str]:
    if factory_path:
        module_name, separator, name = factory_path.partition(":")
        if not separator or not module_name or not name:
            raise ValueError("provider-factory must be module:attribute")
        factory = getattr(importlib.import_module(module_name), name)
        provider = factory(model=model, temperature=temperature)
        identity = factory_path
    else:
        from src.schema.experiment_provider import OpenCodeProvider

        provider = OpenCodeProvider.from_env(model=model, temperature=temperature)
        identity = "OpenCodeProvider (OpenAI-compatible completion API)"
    if not callable(getattr(provider, "generate", None)):
        raise ValueError("Provider factory must return an object with generate(question, schema_context)")
    return provider, identity


def main(argv: list[str] | None = None) -> int:
    """Load explicit CLI configuration and write measured JSON/Markdown reports."""
    # Library imports never read .env; this command explicitly opts into it.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path(os.environ.get("SPIDER_DATA_ROOT", "data/spider_data")))
    parser.add_argument("--cases", type=Path, default=Path("eval/schema_spider_cases.json"))
    parser.add_argument("--backend", choices=("local_graph", "neo4j"), default="local_graph")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--neo4j-database", default=None)
    parser.add_argument("--generate", action="store_true", help="Opt into real model calls for both contexts; disabled by default")
    parser.add_argument("--provider-factory", default=None, help="Optional module:factory accepting model=None, temperature=0")
    parser.add_argument("--model", default=None, help="Override the completion model; otherwise the provider reads configured environment")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--tokenizer-encoding", default=None, help="Optional tiktoken encoding; otherwise report a lexical estimate")
    parser.add_argument("--select-only", action="store_true", help="Regenerate the gold-only case manifest and exit before retrieval")
    parser.add_argument("--case-count", type=int, default=10, help="Even case count used only with --select-only")
    args = parser.parse_args(argv)
    if args.provider_factory and not args.generate:
        parser.error("--provider-factory requires explicit --generate")
    root, cases_path = resolve_path(args.dataset_root), resolve_path(args.cases)
    if args.select_only:
        manifest = select_spider_cases(root, count=args.case_count)
        cases_path.parent.mkdir(parents=True, exist_ok=True)
        cases_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Selected {len(manifest['cases'])} gold-only cases: {cases_path}")
        return 0
    provider, identity = _provider(args.provider_factory, args.model, args.temperature) if args.generate else (None, None)
    report = run_schema_experiment(
        root, load_cases(cases_path), backend=args.backend,
        top_k=args.top_k, repetitions=args.repetitions,
        provider=provider, provider_name=identity, model=args.model,
        temperature=args.temperature, neo4j_database=args.neo4j_database,
        tokenizer=_tokenizer(args.tokenizer_encoding),
    )
    output = resolve_path(args.output or Path(f"eval/results/schema_spider_{args.backend}.json"))
    json_path, markdown_path = write_report(report, output)
    print(render_markdown(report))
    print(f"JSON: {json_path}\nMarkdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
