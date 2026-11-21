"""Poster panel "How we verify": the four verifier layers plus the precision/recall table.

    python scripts/make_verifier_figures.py --results eval/results/verifier_analysis.json \
        --out eval/results/figures/how_we_verify.pdf

Every number is read from the results file written by analyze_verifiers.py. Nothing is typed
by hand. The figure is drawn at final poster size, so a font size in points is the size on paper.
Fonts, sizes and colours come from scripts/poster_style.py (Member 1) when it exists.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:  # Member 1's style module; its API is not published yet, so only these names are assumed.
    import poster_style as style  # type: ignore
    BODY_PT, LABEL_PT = style.BODY_PT, style.LABEL_PT
    INK, ACCENT, SOFT = style.INK, style.ACCENT, style.SOFT
except (ImportError, AttributeError):
    BODY_PT, LABEL_PT = 28, 24  # CLAUDE.md minimums at final poster size
    INK, ACCENT, SOFT = "#1f2933", "#1f6feb", "#e8eef7"

LAYERS = (
    ("Safety", "Blocks anything that changes data"),
    ("Syntax", "Checks the SQL is valid"),
    ("Semantic", "Checks the SQL answers the question"),
    ("Result", "Checks the answer looks sane"),
)
ROWS = (
    ("mismatch", "Says the SQL is wrong"),
    ("not_answerable", "Says it cannot answer"),
    ("assumption_flagged", "States an assumption"),
)


def fmt_rate(r: dict) -> str:
    """'29%  (6/21)' with a star when the sample is too small to mean much."""
    if r["n"] == 0:
        return "n/a (0)"
    return f"{r['pct']:.0f}%  ({r['k']}/{r['n']})" + ("*" if r["too_few"] else "")


def make_panel(analysis: dict, out: Path) -> None:
    plt.rcParams["pdf.fonttype"] = 42  # keep text as real fonts in the vector PDF
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(0.4, 9.45, "How we check every answer", fontsize=BODY_PT + 8, weight="bold", color=INK, va="center")

    box_w, gap = 3.1, 0.2
    for i, (name, blurb) in enumerate(LAYERS):
        x = 0.4 + i * (box_w + gap)
        ax.add_patch(FancyBboxPatch((x, 5.7), box_w, 3.0, boxstyle="round,pad=0.02,rounding_size=0.15",
                                    fc=SOFT, ec=ACCENT, lw=2))
        ax.text(x + box_w / 2, 8.2, name, fontsize=BODY_PT, weight="bold", color=INK, ha="center", va="center")
        ax.text(x + box_w / 2, 6.8, "\n".join(textwrap.wrap(blurb, 15)), fontsize=LABEL_PT, color=INK,
                ha="center", va="center", linespacing=1.15)

    ax.text(0.4, 5.05, "How often the semantic check is right", fontsize=BODY_PT, weight="bold", color=INK, va="center")
    cols = (0.4, 6.4, 10.2)
    for x, head in zip(cols, ("Verdict", "Right when\nit speaks", "Catches\nreal cases")):
        ax.text(x, 4.3, head, fontsize=LABEL_PT, weight="bold", color=ACCENT, va="center", linespacing=1.1)
    ax.plot([0.4, 13.6], [3.8, 3.8], color=ACCENT, lw=2)
    for j, (key, label) in enumerate(ROWS):
        y = 3.3 - j * 0.75
        m = analysis["semantic"][key]
        ax.text(cols[0], y, label, fontsize=LABEL_PT, color=INK, va="center")
        ax.text(cols[1], y, fmt_rate(m["precision"]), fontsize=LABEL_PT, color=INK, va="center")
        ax.text(cols[2], y, fmt_rate(m["recall"]), fontsize=LABEL_PT, color=INK, va="center")
    ax.text(0.4, 0.75, "* Fewer than 5 cases: too few to trust.\nCounts in brackets. Mismatch = SQL was retried.",
            fontsize=LABEL_PT, color=INK, va="center", linespacing=1.2)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="pdf")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=PROJECT_ROOT / "eval/results/verifier_analysis.json")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/results/figures/how_we_verify.pdf")
    args = parser.parse_args(argv)
    make_panel(json.loads(args.results.read_text(encoding="utf-8")), args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
