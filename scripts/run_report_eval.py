"""Run b0, b1 and QueryMind on the report datasets with one live model.

* b0/b1 run through the stakeholder's unchanged baseline
  (`external/agentic-sql-analyst/src/baseline.py`, pinned commit) in its own venv.
* QueryMind runs through `scripts/run_querymind_trace.py`, which writes the
  same trace format.
* Every arm sees the same question IDs, database files and model.

Runs are resumable: a question already present in a trace is skipped. Records
that failed because of the gateway (timeouts, connection or HTTP errors) are
removed and re-run up to --infra-retries times; the counts are kept in the run
manifest. Each database file is hashed before and after
all runs, so "no write executed" is checked, not assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = PROJECT_ROOT / "external/agentic-sql-analyst"
BASELINE_COMMIT = "c0b0cda"
BASELINE_PY = BASELINE_ROOT / "venv/bin/python"
QM_PY = PROJECT_ROOT / ".venv/bin/python"
OUT_ROOT = PROJECT_ROOT / "eval/results/report"
INFRA_ERRORS = {
    "APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError",
    "APIStatusError", "ProviderError",
}
ARMS = ("b0", "b1", "querymind")
# QueryMind arms -> extra CLI options. `querymind` uses the configured schema mode
# (neo4j); `querymind-flat` is the retrieval diagnostic with everything else fixed.
QM_ARMS = {"querymind": [], "querymind-flat": ["--schema-mode", "flat"]}


def datasets() -> dict[str, list[tuple[str, Path, Path]]]:
    """Return dataset -> [(group, questions.yaml, sqlite path)]."""
    spider_root = PROJECT_ROOT / "data/spider_data/database"
    spider = [
        (path.stem, path, spider_root / path.stem / f"{path.stem}.sqlite")
        for path in sorted((PROJECT_ROOT / "eval/spider_pilot/questions").glob("*.yaml"))
    ]
    return {
        "stakeholder": [("main", BASELINE_ROOT / "eval/questions.yaml",
                         PROJECT_ROOT / "data/stakeholder_analytics.db")],
        "spider": spider,
    }


def file_hash(db_path: Path) -> str:
    """Hash the database file bytes; any committed write changes them.

    (A logical SQL dump is not usable here: some Spider databases store text
    that is not valid UTF-8, which `iterdump` cannot decode.)
    """
    return hashlib.sha256(db_path.read_bytes()).hexdigest()


def read_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def drop_infra_failures(path: Path) -> int:
    records = read_trace(path)
    kept = [r for r in records if r.get("error_type") not in INFRA_ERRORS]
    if len(kept) != len(records):
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    return len(records) - len(kept)


def run_arm(arm: str, questions: Path, db_path: Path, trace: Path, ids: list[str],
            env: dict[str, str], model: str, run_tag: str) -> None:
    if arm in QM_ARMS:
        command = [str(QM_PY), "-m", "scripts.run_querymind_trace", "--questions", str(questions),
                   "--db", str(db_path), "--trace", str(trace), "--ids", ",".join(ids), "--run-tag", run_tag,
                   "--arm-name", arm, *QM_ARMS[arm]]
        cwd = PROJECT_ROOT
    else:
        command = [str(BASELINE_PY), "src/baseline.py", "--questions", str(questions), "--ids", ",".join(ids),
                   "--arm", arm, "--provider", "asu", "--model", model, "--db", str(db_path),
                   "--trace", str(trace)]
        cwd = BASELINE_ROOT
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if completed.returncode not in (0, 1):  # baseline exits 1 when any question failed to execute
        sys.stderr.write(completed.stdout[-2000:] + completed.stderr[-2000:])
        raise RuntimeError(f"{arm} run failed with exit code {completed.returncode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("stakeholder", "spider", "all"), default="all")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--repeats", type=int, default=None,
                        help="Override repeats (default: stakeholder 3, spider 1)")
    parser.add_argument("--infra-retries", type=int, default=2)
    parser.add_argument("--model", default="devstral2-123b")
    args = parser.parse_args(argv)

    if not BASELINE_PY.exists():
        parser.error("Stakeholder baseline missing; run `make stakeholder-baseline` first")
    head = subprocess.run(["git", "-C", str(BASELINE_ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if not head.startswith(BASELINE_COMMIT):
        parser.error(f"Stakeholder baseline is at {head}, expected pinned commit {BASELINE_COMMIT}")

    env = {**os.environ, **{k: v for k, v in dotenv_values(PROJECT_ROOT / ".env").items() if v is not None}}
    env["COMPLETION_MODEL"] = args.model
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    selected = datasets() if args.dataset == "all" else {args.dataset: datasets()[args.dataset]}

    manifest_path = OUT_ROOT / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"runs": []}
    for name, groups in selected.items():
        repeats = args.repeats or (3 if name == "stakeholder" else 1)
        before = {str(db): file_hash(db) for _, _, db in groups}
        if name == "spider" and "querymind" in arms:
            ids = [group for group, _, _ in groups]
            subprocess.run([str(QM_PY), "-m", "scripts.build_schema_graph", "--spider-root", "data/spider_data",
                            *sum((["--db-id", i] for i in ids), []), "--upload"],
                           cwd=PROJECT_ROOT, env=env, check=True, capture_output=True)
        entry = {"dataset": name, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "model": args.model, "baseline_commit": head, "repeats": repeats, "arms": arms,
                 "infra_failures_retried": {}}
        for repeat in range(1, repeats + 1):
            for arm in arms:
                for group, questions, db_path in groups:
                    trace = OUT_ROOT / name / f"r{repeat}" / f"{arm}__{group}.jsonl"
                    trace.parent.mkdir(parents=True, exist_ok=True)
                    all_ids = [q["id"] for q in yaml.safe_load(questions.read_text(encoding="utf-8"))]
                    for attempt in range(args.infra_retries + 1):
                        done = {r["question_id"] for r in read_trace(trace)}
                        todo = [i for i in all_ids if i not in done]
                        if not todo:
                            break
                        started = time.time()
                        run_arm(arm, questions, db_path, trace, todo, env, args.model, f"r{repeat}")
                        failed = drop_infra_failures(trace) if attempt < args.infra_retries else 0
                        key = f"r{repeat}/{arm}/{group}"
                        if failed:
                            entry["infra_failures_retried"][key] = entry["infra_failures_retried"].get(key, 0) + failed
                        print(f"{name} r{repeat} {arm:<9} {group:<28} ran {len(todo):>2} "
                              f"in {time.time() - started:6.1f}s; infra failures {failed}", flush=True)
        after = {str(db): file_hash(db) for _, _, db in groups}
        entry["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry["database_file_sha256_unchanged"] = before == after
        entry["database_file_sha256"] = {Path(k).name: v for k, v in after.items()}
        manifest["runs"].append(entry)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"{name}: database contents unchanged = {before == after}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
