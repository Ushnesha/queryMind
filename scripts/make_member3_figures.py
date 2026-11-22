"""Member 3 poster panels: architecture, latency per agent step (R6), ablation (R3).

    python -m scripts.make_member3_figures

Writes vector PDFs (plus PNG previews) to eval/results/poster/:

* m3_architecture.pdf  - pipeline with the R1 flat-schema retry path (no longer "planned")
* m3_latency.pdf       - from eval/results/latency/latency_summary.json (scripts/analyze_latency.py)
* m3_ablation.pdf      - from eval/results/ablation/summary.json (scripts/score_ablation.py)

A panel whose input file is missing is skipped with a message, so the
architecture can be drawn before the poster-freeze runs exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch  # noqa: E402

from scripts.poster_style import (  # noqa: E402
    BEFORE_AFTER, GRID, LABEL_PT, SERIES, SURFACE, TARGET_LINE, TEXT_PRIMARY, TEXT_SECONDARY,
    apply_style, figure, save,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "eval/results/poster"
LATENCY = PROJECT_ROOT / "eval/results/latency/latency_summary.json"
ABLATION = PROJECT_ROOT / "eval/results/ablation/summary.json"

LLM_EDGE = SERIES[0]        # blue: step calls the model
TOOL_EDGE = TEXT_SECONDARY  # grey: deterministic step
NEW_EDGE = SERIES[1]        # orange: R1 retry path (new in Milestone 3)
REFUSE_EDGE = SERIES[7]     # red: refusal exit
UNCLEAR = "#8a8984"

STEP_LABELS = {
    "schema_retriever": "Retrieve schema", "sql_generator": "Generate SQL",
    "safety_verifier": "Safety check", "syntax_verifier": "Syntax check",
    "semantic_verifier": "Semantic check", "optimizer": "Optimize", "executor": "Execute",
    "result_verifier": "Result check", "response_generator": "Write answer",
}
VARIANT_SHORT = {
    "without_neo4j": "Neo4j retrieval", "without_semantic": "Semantic check",
    "without_result_verifier": "Result check", "without_optimizer": "Optimizer",
    "without_schema_retry": "Schema retry", "without_syntax": "Syntax check",
}


# --------------------------------------------------------------------------- architecture
def _box(ax, x, y, w, h, text, edge, *, weight="normal", dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                linewidth=3.5, edgecolor=edge, facecolor="white",
                                linestyle=(0, (4, 2)) if dashed else "solid"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=LABEL_PT,
            color=TEXT_PRIMARY, fontweight=weight, linespacing=1.15)


def _arrow(ax, start, end, color=TEXT_SECONDARY, *, style="-|>", connection="arc3", lw=3.0):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=28, color=color,
                                 linewidth=lw, connectionstyle=connection, shrinkA=0, shrinkB=0))


def architecture(out: Path) -> Path:
    fig, ax = figure("half-tall")
    ax.set_xlim(0, 10.8)
    ax.set_ylim(0, 11)
    ax.axis("off")
    x, w, h, gap, top = 3.15, 5.0, 1.0, 0.42, 9.95
    steps = [
        ("1. Retrieve schema\nNeo4j graph + FK links", TOOL_EDGE),
        ("2. Generate SQL", LLM_EDGE),
        ("3. Verify\nsafety · syntax · meaning", LLM_EDGE),
        ("4. Optimize\n≤2 rounds, same rows", LLM_EDGE),
        ("5. Execute (read-only)", TOOL_EDGE),
        ("6. Check result", LLM_EDGE),
        ("7. Write answer", LLM_EDGE),
    ]
    ys = [top - i * (h + gap) for i in range(len(steps))]
    ax.text(x + w / 2, top + h + 0.45, "Question", ha="center", va="center", fontsize=LABEL_PT,
            fontweight="bold")
    _arrow(ax, (x + w / 2, top + h + 0.2), (x + w / 2, top + h))
    for (text, edge), y in zip(steps, ys):
        _box(ax, x, y, w, h, text, edge)
    for upper, lower in zip(ys, ys[1:]):
        _arrow(ax, (x + w / 2, upper), (x + w / 2, lower + h))
    ax.text(x + w / 2, ys[-1] - 0.45, "Answer + SQL + checks", ha="center", va="center",
            fontsize=LABEL_PT, fontweight="bold")
    _arrow(ax, (x + w / 2, ys[-1]), (x + w / 2, ys[-1] - 0.22))

    gen_y, ver_y = ys[1], ys[2]
    # Repair loop (right): verification failure -> regenerate with feedback.
    right = x + w
    _arrow(ax, (right, ver_y + h / 2), (right, gen_y + h / 2), connection="arc3,rad=0.9")
    ax.text(right + 1.05, (gen_y + ver_y + h) / 2, "repair\n≤3", ha="left", va="center",
            fontsize=LABEL_PT, color=TEXT_SECONDARY)

    # R1 flat-schema retry (left): a refusal in Neo4j mode retries once with the full schema.
    rx, rw = 0.1, 2.55
    _box(ax, rx, ver_y - 0.3, rw, h + 0.6, "Refused?\nretry once,\nfull schema", NEW_EDGE, weight="bold")
    _arrow(ax, (x, ver_y + h / 2), (rx + rw, ver_y + h / 2), NEW_EDGE)
    _arrow(ax, (rx + rw / 2, ver_y + h + 0.3), (x, gen_y + h / 2), NEW_EDGE, connection="angle,angleA=90,angleB=180")
    _box(ax, rx, ys[4] - 0.1, rw, h + 0.2, "Refuse +\nname the gap", REFUSE_EDGE)
    _arrow(ax, (rx + rw / 2, ver_y - 0.3), (rx + rw / 2, ys[4] + h + 0.1), REFUSE_EDGE)

    ax.legend(handles=[Patch(facecolor="white", edgecolor=LLM_EDGE, linewidth=3.5, label="calls the LLM"),
                       Patch(facecolor="white", edgecolor=TOOL_EDGE, linewidth=3.5, label="deterministic"),
                       Patch(facecolor="white", edgecolor=NEW_EDGE, linewidth=3.5, label="new: R1 retry")],
              loc="lower center", bbox_to_anchor=(0.5, -0.02), ncol=3, handlelength=1.0, columnspacing=1.0,
              fontsize=LABEL_PT)
    return save(fig, out / "m3_architecture")


# --------------------------------------------------------------------------- latency
def latency(summary: dict, out: Path) -> Path:
    before, after = summary["before_answered"], summary["after_answered"]
    fig, (top, bottom) = figure("half-tall", nrows=2, gridspec_kw={"height_ratios": [1.3, 1]})

    # Top: mean time per answered question, split by agent step.
    rows = [("Milestone 2", before), ("After R6", after)]
    for index, (label, data) in enumerate(rows):
        y = len(rows) - 1 - index
        per_node = data.get("per_node") or {}
        if not per_node:
            if data.get("mean_s") is not None:
                top.barh(y, data["mean_s"], color=BEFORE_AFTER["before"], height=0.6)
                top.text(data["mean_s"] / 2, y, "per-step time\nnot logged", ha="center", va="center",
                         color="white", fontsize=LABEL_PT)
            continue
        left = 0.0
        for colour, (node, item) in zip(SERIES * 2, per_node.items()):
            top.barh(y, item["mean_s"], left=left, color=colour, height=0.6,
                     label=STEP_LABELS.get(node, node) if index == 1 else None)
            left += item["mean_s"]
        top.text(left, y, f" {left:.1f} s", va="center", fontsize=LABEL_PT)
    top.set_yticks(range(len(rows)), [label for label, _ in reversed(rows)])
    top.set_xlabel("Mean seconds per answered question")
    top.margins(x=0.18)
    top.grid(axis="x", color=GRID)
    top.grid(axis="y", visible=False)
    if after.get("per_node"):
        top.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, fontsize=LABEL_PT,
                   handlelength=1.0, columnspacing=1.2)

    # Bottom: p50/p95 on answered questions against the 15 s target.
    labels = ("p50", "p95")
    width = 0.38
    peak = 0.0
    for offset, (name, data) in zip((-width / 2, width / 2), (("before", before), ("after", after))):
        values = [data.get("p50_answered_s"), data.get("p95_answered_s")]
        xs = [i + offset for i in range(len(labels))]
        bars = bottom.bar([x for x, v in zip(xs, values) if v is not None],
                          [v for v in values if v is not None], width=width,
                          color=BEFORE_AFTER[name], label="Milestone 2" if name == "before" else "After R6")
        bottom.bar_label(bars, fmt="%.1f", fontsize=LABEL_PT, padding=4)
        peak = max([peak, *[v for v in values if v is not None]])
    target = summary.get("target_p50_answered_s", 15.0)
    bottom.axhline(target, color=TARGET_LINE, linestyle="--", linewidth=2.5)
    bottom.text(1.62, target * 1.08, f"{target:.0f} s target", va="bottom", ha="left", fontsize=LABEL_PT)
    bottom.set_xlim(-0.6, 2.25)
    bottom.set_ylim(0, max(peak, target) * 1.55)
    bottom.set_xticks(range(len(labels)), [f"{label}, answered" for label in labels])
    bottom.set_ylabel("Seconds")
    bottom.legend(loc="upper left", ncol=2, fontsize=LABEL_PT, handlelength=1.0)
    return save(fig, out / "m3_latency")


# --------------------------------------------------------------------------- ablation
# (metric, legend label, higher_is_better). Lower-is-better metrics are sign-flipped
# so that, for every metric, a point left of 0 means "worse without this agent".
ABLATION_METRICS = (("correct_all", "Correct answers", True),
                    ("over_refusal", "Avoids over-refusal", False),
                    ("fabrications", "Avoids fabrication", False))


def ablation(summary: dict, out: Path, dataset: str | None = None) -> Path:
    datasets = summary["datasets"]
    name = dataset or ("stakeholder60" if "stakeholder60" in datasets else next(iter(datasets)))
    table = datasets[name]["variants"]
    variants = [v for v in VARIANT_SHORT if v in table]
    fig, ax = figure("half")
    offsets = (0.22, 0.0, -0.22)
    for colour, offset, (key, label, higher) in zip(SERIES, offsets, ABLATION_METRICS):
        for row, variant in enumerate(reversed(variants)):
            delta = (table[variant]["metrics"].get(key) or {}).get("delta_pp")
            if not delta:
                continue
            diff, low, high = delta if higher else (-delta[0], -delta[2], -delta[1])
            conclusive = low > 0 or high < 0
            ax.errorbar(diff, row + offset, xerr=[[diff - low], [high - diff]], fmt="o", color=colour,
                        ecolor=colour, elinewidth=3, capsize=5, markersize=13, markeredgewidth=3,
                        markerfacecolor=colour if conclusive else "white")
        ax.plot([], [], "o", color=colour, markersize=13, label=label)
    ax.plot([], [], "o", color=UNCLEAR, markerfacecolor="white", markeredgewidth=3, markersize=13,
            label="hollow: CI includes 0")
    ax.axvline(0, color=TARGET_LINE, linewidth=2)
    ax.set_yticks(range(len(variants)), [VARIANT_SHORT[v] for v in reversed(variants)])
    ax.set_xlabel("Change when removed (pp)  ← worse | better →")
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    fig.legend(loc="outside lower center", ncol=2, fontsize=LABEL_PT, handlelength=1.0, columnspacing=1.2)
    return save(fig, out / "m3_ablation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--latency", type=Path, default=LATENCY)
    parser.add_argument("--ablation", type=Path, default=ABLATION)
    parser.add_argument("--ablation-dataset", help="stakeholder60 (default when present) or stakeholder")
    args = parser.parse_args(argv)
    apply_style()
    written = [architecture(args.out)]
    if args.latency.exists():
        written.append(latency(json.loads(args.latency.read_text(encoding="utf-8")), args.out))
    else:
        print(f"skipped latency panel: {args.latency} missing (run scripts/analyze_latency.py)")
    if args.ablation.exists():
        written.append(ablation(json.loads(args.ablation.read_text(encoding="utf-8")), args.out,
                                args.ablation_dataset))
    else:
        print(f"skipped ablation panel: {args.ablation} missing (run scripts/score_ablation.py)")
    for path in written:
        print(f"wrote {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
