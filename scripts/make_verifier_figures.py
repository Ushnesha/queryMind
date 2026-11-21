"""Poster panel "How we verify": the four verifier layers plus the precision/recall table.

    python scripts/make_verifier_figures.py --results eval/results/verifier_analysis.json \
        --out eval/results/poster/how_we_verify.pdf

Every number is read from the results file written by analyze_verifiers.py. Nothing is typed
by hand. The panel is drawn at final poster size ("half-tall", 10.8 x 11 in), so a font size
in points is the size on paper. Fonts, colours and sizes come from scripts/poster_style.py
(Member 1). Until that module is on this branch a small local stand-in is used.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # headless: no window, works in tests and on any machine
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

try:
    from scripts.poster_style import ARM_COLORS, BODY_PT, LABEL_PT, TEXT_PRIMARY, apply_style, figure, save
    ACCENT = ARM_COLORS["querymind"]
except ImportError:  # stand-in with the same minimum sizes, replaced by the real module once merged
    BODY_PT, LABEL_PT, TEXT_PRIMARY, ACCENT = 28, 24, "#0b0b0b", "#2a78d6"

    def apply_style() -> None:
        plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"],
                             "pdf.fonttype": 42})

    def figure(size: str = "half-tall"):
        return plt.subplots(figsize=(10.8, 11.0), layout="constrained")

    def save(fig, path):
        path = Path(path).with_suffix(".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        return path

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


def make_panel(analysis: dict, out: Path) -> Path:
    apply_style()
    fig, ax = figure("half-tall")
    ax.set_xlim(0, 10.8)
    ax.set_ylim(0, 11)
    ax.axis("off")

    ax.text(0.1, 10.5, "How we check every answer", fontsize=BODY_PT, weight="bold", color=TEXT_PRIMARY, va="center")

    box_w, box_h, gap = 5.2, 1.9, 0.2
    for i, (name, blurb) in enumerate(LAYERS):
        x = 0.1 + (i % 2) * (box_w + gap)
        y = 7.9 - (i // 2) * (box_h + gap)
        ax.add_patch(FancyBboxPatch((x, y), box_w, box_h, boxstyle="round,pad=0.02,rounding_size=0.15",
                                    fc=to_rgba(ACCENT, 0.12), ec=ACCENT, lw=2))
        ax.text(x + 0.25, y + box_h - 0.5, name, fontsize=BODY_PT, weight="bold", color=TEXT_PRIMARY, va="center")
        ax.text(x + 0.25, y + 0.65, "\n".join(textwrap.wrap(blurb, 24)), fontsize=LABEL_PT, color=TEXT_PRIMARY,
                va="center", linespacing=1.15)

    ax.text(0.1, 4.65, "How often the semantic check is right", fontsize=BODY_PT, weight="bold",
            color=TEXT_PRIMARY, va="center")
    cols = (0.1, 4.7, 7.9)
    for x, head in zip(cols, ("Verdict", "Right when\nit speaks", "Catches\nreal cases")):
        ax.text(x, 3.85, head, fontsize=LABEL_PT, weight="bold", color=ACCENT, va="center", linespacing=1.1)
    ax.plot([0.1, 10.7], [3.3, 3.3], color=ACCENT, lw=2)
    for j, (key, label) in enumerate(ROWS):
        y = 2.7 - j * 0.7
        m = analysis["semantic"][key]
        ax.text(cols[0], y, label, fontsize=LABEL_PT, color=TEXT_PRIMARY, va="center")
        ax.text(cols[1], y, fmt_rate(m["precision"]), fontsize=LABEL_PT, color=TEXT_PRIMARY, va="center")
        ax.text(cols[2], y, fmt_rate(m["recall"]), fontsize=LABEL_PT, color=TEXT_PRIMARY, va="center")
    ax.text(0.1, 0.45, "* Fewer than 5 cases: too few to trust.\nCounts in brackets. Mismatch = SQL was retried.",
            fontsize=LABEL_PT, color=TEXT_PRIMARY, va="center", linespacing=1.2)
    return save(fig, out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=PROJECT_ROOT / "eval/results/verifier_analysis.json")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/results/poster/how_we_verify.pdf")
    args = parser.parse_args(argv)
    print(f"wrote {make_panel(json.loads(args.results.read_text(encoding='utf-8')), args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
