"""Build Member 1's poster panels from the scored report results.

Reads `eval/results/report/summary.json` (written by `scripts/score_report_eval.py`)
and writes, under `eval/results/poster/`:

* `results_table.pdf` / `.tex` / `.md` - main results table, b0 / b1 / b2 / QueryMind /
  QueryMind-flat, run r1 with 95% Wilson intervals and exact McNemar p vs b1.
* `metrics_vs_targets.pdf` - key metrics per system against the stakeholder's targets.
* `honest_results.md` / `.tex` - where QueryMind does and does not beat b1.
* `poster_numbers.json` - every number used above, for the pre-submission number check.

The 60-question set is used when it has been scored; otherwise the 17-question set
(plan section 4 fallback), and the panels say which one they show.

    .venv/bin/python -m scripts.make_poster_figures [--dataset stakeholder60]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.poster_style import (  # noqa: E402
    ARMS, GRID, LABEL_PT, TARGET_LINE, TEXT_PRIMARY, TEXT_SECONDARY, apply_style, arm_color, arm_label,
    figure, save,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = PROJECT_ROOT / "eval/results/report/summary.json"
OUT_DIR = PROJECT_ROOT / "eval/results/poster"
DATASET_LABEL = {"stakeholder60": "60-question set", "stakeholder": "17-question set", "spider": "Spider pilot"}

# Stakeholder targets (external/agentic-sql-analyst/PROPOSAL.md section 6).
# (metric key, short label, direction, target as a fraction or callable of n, target text)
RATE_METRICS = [
    ("set_easy", "Easy\naccuracy", "higher", lambda n: 1.0, "100%"),
    ("set_hard", "Hard\naccuracy", "higher", lambda n: 0.70, "≥70%"),
    ("ambiguity_flagged", "Ambiguity\nflagged", "higher", lambda n: 0.75, "≥75%"),
    ("exec_success", "Execution\nsuccess", "higher", lambda n: 0.98, "≥98%"),
    ("fabrications", "False answers\n(unanswerable)", "lower", lambda n: 1 / 15, "≤1/15"),
    ("over_refusal", "Over-\nrefusal", "lower", lambda n: 1 / n if n else 0.0, "≤1"),
]
LATENCY_TARGET_S = 15.0
# Rows of the main results table: (key, label, direction)
TABLE_ROWS = [
    ("set_easy", "Easy accuracy", "higher"),
    ("set_hard", "Hard accuracy", "higher"),
    ("unanswerable_refused_correctly", "Unanswerable: correct refusal", "higher"),
    ("fabrications", "False answers on unanswerable", "lower"),
    ("ambiguity_flagged", "Ambiguity flagged", "higher"),
    ("over_refusal", "Over-refusal", "lower"),
    ("exec_success", "Execution success", "higher"),
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pick_dataset(report: dict, wanted: str | None) -> str:
    available = report.get("datasets", {})
    if wanted:
        if wanted not in available:
            raise SystemExit(f"Dataset {wanted!r} not scored in summary; available: {sorted(available)}")
        return wanted
    for name in ("stakeholder60", "stakeholder"):
        if name in available:
            return name
    raise SystemExit("No stakeholder dataset in summary; run scripts/score_report_eval.py first")


def primary(report: dict, dataset: str) -> dict[str, dict]:
    """Run r1 summaries for the arms present, in poster order."""
    r1 = report["datasets"][dataset]["summaries"].get("r1", {})
    return {arm: r1[arm] for arm in ARMS if arm in r1}


def frac(value) -> tuple[int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2 and value[1]:
        return int(value[0]), int(value[1])
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval as fractions (same formula as the stakeholder's score.wilson)."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cell(value) -> str:
    pair = frac(value)
    if pair is None:
        return "—"
    k, n = pair
    low, high = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%; {100 * low:.0f}–{100 * high:.0f})"


# --------------------------------------------------------------------------- #
# Results table
# --------------------------------------------------------------------------- #

def table_rows(arms: dict[str, dict], paired: dict) -> list[list[str]]:
    rows = []
    for key, label, direction in TABLE_ROWS:
        if not any(frac(s.get(key)) for s in arms.values()):
            continue
        arrow = "↑" if direction == "higher" else "↓"
        rows.append([f"{label} {arrow}"] + [cell(s.get(key)) for s in arms.values()])
    rows.append(["p50 latency, answered (s) ↓"] + [
        f"{s['latency_answered_s']['p50']:.1f}" if (s.get("latency_answered_s") or {}).get("p50") is not None
        else "—" for s in arms.values()])
    rows.append(["LLM calls / question ↓"] + [
        f"{s['llm_calls_per_question']:.1f}" if s.get("llm_calls_per_question") is not None else "—"
        for s in arms.values()])
    rows.append(["Tokens / question ↓"] + [
        f"{s['tokens_per_question']:.0f}" if s.get("tokens_per_question") is not None else "—"
        for s in arms.values()])
    mcnemar = []
    for arm in arms:
        pair = paired.get(f"{arm} vs b1")
        mcnemar.append("ref." if arm == "b1" else
                       f"+{pair['a_only']} / −{pair['b_only']}, p={pair['p_exact_mcnemar']:.2f}" if pair else "—")
    rows.append(["vs b1: wins / losses, McNemar p"] + mcnemar)
    return rows


def write_table(arms: dict[str, dict], paired: dict, dataset: str, out: Path) -> dict:
    header = ["Metric (run r1)"] + [arm_label(a) for a in arms]
    rows = table_rows(arms, paired)
    caption = (f"{DATASET_LABEL.get(dataset, dataset)}, run r1, one model (devstral2-123b). "
               "k/n (%; 95% Wilson CI). Scored by the stakeholder's unmodified scorer.")

    md = ["| " + " | ".join(header) + " |", "|---|" + "---:|" * len(arms)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    (out / "results_table.md").write_text(caption + "\n\n" + "\n".join(md) + "\n", encoding="utf-8")

    def tex_escape(text: str) -> str:
        return (text.replace("%", r"\%").replace("&", r"\&").replace("_", r"\_").replace("≥", r"$\geq$")
                .replace("≤", r"$\leq$").replace("↑", r"$\uparrow$").replace("↓", r"$\downarrow$")
                .replace("−", "--").replace("—", "---"))
    tex = [r"\begin{tabular}{l" + "r" * len(arms) + "}", r"\toprule",
           " & ".join(tex_escape(h) for h in header) + r" \\", r"\midrule"]
    tex += [" & ".join(tex_escape(c) for c in r) + r" \\" for r in rows]
    tex += [r"\bottomrule", r"\end{tabular}"]
    (out / "results_table.tex").write_text("% " + caption + "\n" + "\n".join(tex) + "\n", encoding="utf-8")

    fig, ax = figure("full")
    ax.axis("off")
    ax.grid(False)
    table = ax.table(cellText=rows, colLabels=header, loc="upper center", cellLoc="right", colLoc="right",
                     colWidths=[0.31] + [0.69 / len(arms)] * len(arms))
    table.auto_set_font_size(False)
    table.set_fontsize(LABEL_PT - 4 if len(arms) > 4 else LABEL_PT - 2)
    table.scale(1, 3.0)
    qm_col = list(arms).index("querymind") + 1 if "querymind" in arms else None
    for (r, c), item in table.get_celld().items():
        item.set_edgecolor(GRID)
        item.set_linewidth(1.0)
        if c == 0:
            item.set_text_props(ha="left", color=TEXT_PRIMARY)
            item._loc = "left"
        if r == 0:
            item.set_text_props(weight="bold", color=TEXT_PRIMARY)
        if c == qm_col:
            item.set_text_props(weight="bold")
    ax.set_title("Results: every system on the same questions, model and scorer", pad=12)
    fig.text(0.01, 0.01, caption, fontsize=LABEL_PT - 6, color=TEXT_SECONDARY)
    save(fig, out / "results_table")
    return {"header": header, "rows": rows, "caption": caption}


# --------------------------------------------------------------------------- #
# Bar chart against targets
# --------------------------------------------------------------------------- #

def metrics_chart(arms: dict[str, dict], dataset: str, out: Path) -> dict:
    metrics = [m for m in RATE_METRICS if any(frac(s.get(m[0])) for s in arms.values())]
    fig, (ax, ax_lat) = figure("full", ncols=2, width_ratios=[len(metrics), 1.4])
    width = 0.8 / len(arms)
    plotted: dict = {}
    for i, (arm, s) in enumerate(arms.items()):
        xs, ys, lo, hi = [], [], [], []
        for j, (key, *_rest) in enumerate(metrics):
            pair = frac(s.get(key))
            if pair is None:
                continue
            k, n = pair
            low, high = wilson(k, n)
            xs.append(j - 0.4 + width * (i + 0.5))
            ys.append(100 * k / n)
            lo.append(max(0.0, 100 * (k / n - low)))
            hi.append(max(0.0, 100 * (high - k / n)))
            plotted.setdefault(arm, {})[key] = [k, n]
        bars = ax.bar(xs, ys, width=width * 0.9, color=arm_color(arm), label=arm_label(arm),
                      edgecolor="white", linewidth=2)
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor=TEXT_SECONDARY, elinewidth=1.5, capsize=4)
        for bar, y in zip(bars, ys):
            ax.annotate(f"{y:.0f}", (bar.get_x() + bar.get_width() / 2, 1.5), ha="center", va="bottom",
                        fontsize=LABEL_PT - 8, color="white" if y >= 9 else TEXT_PRIMARY,
                        xytext=(0, 0), textcoords="offset points", rotation=90 if len(arms) > 4 else 0)
    targets = {}
    for j, (key, label, direction, target, text) in enumerate(metrics):
        n = max((frac(s.get(key)) or (0, 0))[1] for s in arms.values())
        y = 100 * target(n)
        targets[key] = {"target_pct": y, "text": text, "direction": direction}
        ax.hlines(y, j - 0.45, j + 0.45, colors=TARGET_LINE, linestyles=(0, (4, 2)), linewidth=2.5, zorder=5)
        ax.annotate(f"target {text}", (j, y), xytext=(0, 6), textcoords="offset points", ha="center",
                    fontsize=LABEL_PT - 6, color=TEXT_PRIMARY, zorder=6)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels([("↑ " if m[2] == "higher" else "↓ ") + m[1] for m in metrics])
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("% of questions (run r1, 95% CI)")
    ax.set_title(f"Key metrics vs stakeholder targets ({DATASET_LABEL.get(dataset, dataset)})")

    lat = {arm: (s.get("latency_answered_s") or {}).get("p50") for arm, s in arms.items()}
    lat = {arm: v for arm, v in lat.items() if v is not None}
    bars = ax_lat.bar(range(len(lat)), list(lat.values()), color=[arm_color(a) for a in lat],
                      edgecolor="white", linewidth=2)
    for bar, value in zip(bars, lat.values()):
        ax_lat.annotate(f"{value:.1f}", (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=LABEL_PT - 6, color=TEXT_PRIMARY)
    ax_lat.axhline(LATENCY_TARGET_S, color=TARGET_LINE, linestyle=(0, (4, 2)), linewidth=2.5)
    ax_lat.annotate("target <15 s", ((len(lat) - 1) / 2, LATENCY_TARGET_S), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=LABEL_PT - 6)
    ax_lat.set_xticks([])
    ax_lat.set_ylim(0, max([LATENCY_TARGET_S * 1.25, *(v * 1.2 for v in lat.values())]))
    ax_lat.set_ylabel("answered questions only")
    ax_lat.set_title("↓ p50 latency (s)")
    fig.legend(*ax.get_legend_handles_labels(), loc="outside lower center", ncols=len(arms))
    save(fig, out / "metrics_vs_targets")
    return {"rates": plotted, "targets": targets, "p50_latency_answered_s": lat}


# --------------------------------------------------------------------------- #
# Honest results box
# --------------------------------------------------------------------------- #

def honest_results(arms: dict[str, dict], paired: dict, dataset: str, out: Path) -> dict:
    qm, b1 = arms.get("querymind"), arms.get("b1")
    if qm is None or b1 is None:
        text = "QueryMind or b1 has not been scored on this dataset yet."
        (out / "honest_results.md").write_text(text + "\n", encoding="utf-8")
        return {"note": text}
    better, same, worse = [], [], []
    for key, label, direction in TABLE_ROWS:
        a, b = frac(qm.get(key)), frac(b1.get(key))
        if a is None or b is None:
            continue
        ra, rb = a[0] / a[1], b[0] / b[1]
        item = f"{label}: {a[0]}/{a[1]} vs {b[0]}/{b[1]}"
        if math.isclose(ra, rb):
            same.append(item)
        elif (ra > rb) == (direction == "higher"):
            better.append(item)
        else:
            worse.append(item)
    cost = []
    for key, label in (("llm_calls_per_question", "LLM calls"), ("tokens_per_question", "tokens")):
        if qm.get(key) and b1.get(key):
            cost.append(f"{qm[key] / b1[key]:.1f}× the {label} of b1")
    lat_qm = (qm.get("latency_answered_s") or {}).get("p50")
    lat_b1 = (b1.get("latency_answered_s") or {}).get("p50")
    if lat_qm is not None and lat_b1 is not None:
        cost.append(f"p50 latency on answered questions {lat_qm:.1f} s vs {lat_b1:.1f} s")
    pair = paired.get("querymind vs b1")
    overall = (f"Overall (all questions, paired): QueryMind alone correct on {pair['a_only']}, b1 alone on "
               f"{pair['b_only']}; exact McNemar p = {pair['p_exact_mcnemar']:.2f}."
               + (" Not a significant difference at n = " + str(pair["n"]) + "."
                  if pair["p_exact_mcnemar"] >= 0.05 else "")) if pair else ""
    sections = [
        ("Where QueryMind beats b1", better or ["None on this set."]),
        ("Where it does not", worse + [f"Tie — {s}" for s in same] or ["None."]),
        ("What it costs", cost or ["Not measured."]),
    ]
    md = [f"**Honest results ({DATASET_LABEL.get(dataset, dataset)}, run r1)**", ""]
    for title, items in sections:
        md += [f"*{title}*", *[f"- {i}" for i in items], ""]
    if overall:
        md.append(overall)
    (out / "honest_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    tex = [r"\textbf{Honest results} (" + DATASET_LABEL.get(dataset, dataset) + ", run r1)"]
    for title, items in sections:
        tex += [r"\par\textit{" + title + r"}", r"\begin{itemize}"]
        tex += [r"\item " + i.replace("%", r"\%").replace("×", r"$\times$") for i in items]
        tex += [r"\end{itemize}"]
    if overall:
        tex.append(overall)
    (out / "honest_results.tex").write_text("\n".join(tex) + "\n", encoding="utf-8")
    return {"better": better, "worse": worse, "same": same, "cost": cost, "overall": overall}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--dataset", choices=sorted(DATASET_LABEL))
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    report = load_summary(args.summary)
    dataset = pick_dataset(report, args.dataset)
    arms = primary(report, dataset)
    if not arms:
        raise SystemExit(f"No r1 results for {dataset}")
    paired = report["datasets"][dataset].get("paired_r1", {})
    args.out.mkdir(parents=True, exist_ok=True)
    apply_style()
    numbers = {
        "summary": str(args.summary),
        "dataset": dataset,
        "arms": list(arms),
        "manifest_runs": [{k: run.get(k) for k in ("dataset", "started", "model", "querymind_commit", "repeats")}
                          for run in report.get("manifest", {}).get("runs", [])],
        "table": write_table(arms, paired, dataset, args.out),
        "chart": metrics_chart(arms, dataset, args.out),
        "honest_results": honest_results(arms, paired, dataset, args.out),
        "paired_r1": paired,
    }
    (args.out / "poster_numbers.json").write_text(json.dumps(numbers, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    print(f"Wrote poster panels for {dataset} ({', '.join(arms)}) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
