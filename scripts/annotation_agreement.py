"""Agreement between two annotators who labeled the same questions (Task 2).

    python scripts/annotation_agreement.py --a eval/annotations/member4_ambiguous.yaml \
        --b eval/annotations/<first_annotator>.yaml --field label --out eval/results/annotation_agreement.json

Each file is a YAML list of {id, <field>: value, ...}. Only ids present in BOTH files with a
non-empty label are compared. Reports raw percent agreement (with counts and a 95% Wilson
interval) and Cohen's kappa. Kappa corrects for chance: 1 is perfect, 0 is no better than chance.
It is undefined (None) when both annotators used one single label for every question.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_verifiers import rate  # noqa: E402


def load_labels(path: Path, field: str) -> dict[str, str]:
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {str(i["id"]): str(i[field]) for i in items if i.get(field) not in (None, "")}


def agreement(a: dict[str, str], b: dict[str, str]) -> dict:
    ids = sorted(a.keys() & b.keys())
    if not ids:
        raise ValueError("no question has a label from both annotators")
    n = len(ids)
    agree = sum(a[i] == b[i] for i in ids)
    count_a, count_b = Counter(a[i] for i in ids), Counter(b[i] for i in ids)
    chance = sum(count_a[label] * count_b[label] for label in count_a) / n ** 2  # both pick the same label by luck
    observed = agree / n
    return {
        "n": n,
        "raw_agreement": rate(agree, n),
        "chance_agreement": chance,
        "kappa": None if chance == 1 else (observed - chance) / (1 - chance),
        "pairs": dict(Counter(f"{a[i]} | {b[i]}" for i in ids)),
        "disagreements": [i for i in ids if a[i] != b[i]],
        "only_in_first_file": sorted(a.keys() - b.keys()),
        "only_in_second_file": sorted(b.keys() - a.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--field", default="label")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/results/annotation_agreement.json")
    args = parser.parse_args(argv)
    result = agreement(load_labels(args.a, args.field), load_labels(args.b, args.field))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    raw = result["raw_agreement"]
    kappa = "undefined" if result["kappa"] is None else f"{result['kappa']:.2f}"
    print(f"agreement {raw['k']}/{raw['n']} ({raw['pct']:.0f}%, CI {raw['ci_low']:.0f}-{raw['ci_high']:.0f}), "
          f"kappa {kappa}; disagreements: {result['disagreements'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
