"""R3: live per-agent ablation on the stakeholder question set (one factor off per variant).

Each variant switches exactly one thing off relative to the full Neo4j pipeline
(`src.evaluation.ablation.experiment_variants`) and writes stakeholder-format
traces, so `scripts/score_ablation.py` can score them with the stakeholder's
unchanged scorer:

    eval/results/ablation/<dataset>/r<k>/<variant>__main.jsonl

Gateway quota (plan section 3, Member 3): the default is the 60-question set
x 1 repeat, or the 17-question set x 3 repeats. The two arms the main
evaluation already ran are reused instead of re-run (``--reuse-report``):

    all_enabled   <- eval/results/report/<dataset>/r<k>/querymind__main.jsonl
    without_neo4j <- eval/results/report/<dataset>/r<k>/querymind-flat__main.jsonl

Only run this after R1 and R6 are merged, otherwise it measures the old pipeline.
Runs are resumable and gateway failures are re-run like `run_report_eval.py`.

    python -m scripts.run_live_ablation --dataset stakeholder60
    python -m scripts.run_live_ablation --dataset stakeholder --repeats 3
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from src.evaluation.ablation import experiment_variants

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = PROJECT_ROOT / "eval/results/ablation"
REPORT_ROOT = PROJECT_ROOT / "eval/results/report"
# Arms of the main evaluation that are identical to an ablation variant.
REUSABLE = {"all_enabled": "querymind", "without_neo4j": "querymind-flat"}
SWITCH_NAMES = {
    "enable_syntax": "syntax", "enable_semantic": "semantic", "enable_optimizer": "optimizer",
    "enable_result_verifier": "result_verifier", "enable_schema_retry": "schema_retry",
}
DEFAULT_REPEATS = {"stakeholder60": 1, "stakeholder": 3}


def variant_cli(flags: dict) -> list[str]:
    """Translate one experiment variant into `run_querymind_trace` options."""
    options = ["--schema-mode", str(flags.get("schema_mode", "neo4j"))]
    for key, name in SWITCH_NAMES.items():
        if flags.get(key) is False:
            options += ["--disable", name]
    return options


def interpreter() -> str:
    venv = PROJECT_ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    return str(venv) if venv.exists() else sys.executable


def read_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [json.loads(line)["question_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    from scripts.run_report_eval import datasets, drop_infra_failures, file_hash

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=tuple(DEFAULT_REPEATS), default="stakeholder60")
    parser.add_argument("--repeats", type=int, help="Default: stakeholder60 1, stakeholder 3")
    parser.add_argument("--variants", help="Comma-separated subset (default: all six)")
    parser.add_argument("--include-syntax", action="store_true", help="Also run without_syntax (more quota)")
    parser.add_argument("--no-reuse-report", dest="reuse_report", action="store_false",
                        help="Re-run all_enabled/without_neo4j instead of copying the main evaluation's traces")
    parser.add_argument("--infra-retries", type=int, default=2)
    parser.add_argument("--model", default="devstral2-123b")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and the estimated runs only")
    args = parser.parse_args(argv)

    variants = experiment_variants(include_syntax=args.include_syntax)
    if args.variants:
        wanted = [name.strip() for name in args.variants.split(",") if name.strip()]
        unknown = sorted(set(wanted) - set(variants))
        if unknown:
            parser.error(f"Unknown variant(s) {unknown}; choose from {sorted(variants)}")
        variants = {name: variants[name] for name in wanted}
    repeats = args.repeats or DEFAULT_REPEATS[args.dataset]
    ((group, questions, db_path),) = datasets()[args.dataset]
    if not questions.exists():
        parser.error(f"Question file missing: {questions}")
    all_ids = [item["id"] for item in yaml.safe_load(questions.read_text(encoding="utf-8"))]

    plan = []
    for repeat in range(1, repeats + 1):
        for name, flags in variants.items():
            source = REPORT_ROOT / args.dataset / f"r{repeat}" / f"{REUSABLE.get(name, '')}__{group}.jsonl"
            reuse = args.reuse_report and name in REUSABLE and set(all_ids) <= set(read_ids(source))
            plan.append((repeat, name, flags, source if reuse else None))
    live = sum(1 for *_, source in plan if source is None)
    print(f"{args.dataset}: {len(all_ids)} questions x {len(plan)} variant-runs "
          f"({live} live, {len(plan) - live} reused) ~ {live * len(all_ids)} questions through the gateway")
    for repeat, name, flags, source in plan:
        print(f"  r{repeat} {name:<24} " + (f"reuse {source.relative_to(PROJECT_ROOT)}" if source
                                             else " ".join(variant_cli(flags))))
    if args.dry_run:
        return 0
    if not db_path.exists():
        parser.error(f"Database missing: {db_path}; run `make stakeholder-baseline` first")

    env = dict(os.environ, COMPLETION_MODEL=args.model)
    before = file_hash(db_path)
    manifest_path = OUT_ROOT / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"runs": []}
    entry = {
        "dataset": args.dataset, "repeats": repeats, "model": args.model,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "querymind_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                           capture_output=True, text=True).stdout.strip(),
        "variants": {name: flags for name, flags in variants.items()},
        "reused": {}, "infra_failures_retried": {},
    }
    for repeat, name, flags, source in plan:
        trace = OUT_ROOT / args.dataset / f"r{repeat}" / f"{name}__{group}.jsonl"
        trace.parent.mkdir(parents=True, exist_ok=True)
        if source is not None:
            shutil.copyfile(source, trace)
            entry["reused"][f"r{repeat}/{name}"] = str(source.relative_to(PROJECT_ROOT))
            continue
        for attempt in range(args.infra_retries + 1):
            todo = [qid for qid in all_ids if qid not in set(read_ids(trace))]
            if not todo:
                break
            started = time.time()
            command = [interpreter(), "-m", "scripts.run_querymind_trace", "--questions", str(questions),
                       "--db", str(db_path), "--trace", str(trace), "--ids", ",".join(todo),
                       "--run-tag", f"r{repeat}", "--arm-name", name, *variant_cli(flags)]
            completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
            if completed.returncode != 0:
                sys.stderr.write(completed.stdout[-2000:] + completed.stderr[-2000:])
                raise RuntimeError(f"{name} r{repeat} failed with exit code {completed.returncode}")
            failed = drop_infra_failures(trace) if attempt < args.infra_retries else 0
            if failed:
                key = f"r{repeat}/{name}"
                entry["infra_failures_retried"][key] = entry["infra_failures_retried"].get(key, 0) + failed
            print(f"r{repeat} {name:<24} ran {len(todo):>2} in {time.time() - started:6.1f}s; "
                  f"infra failures {failed}", flush=True)
    entry["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry["database_file_sha256_unchanged"] = before == file_hash(db_path)
    manifest["runs"].append(entry)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Database contents unchanged = {entry['database_file_sha256_unchanged']}; "
          f"score with scripts/score_ablation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
