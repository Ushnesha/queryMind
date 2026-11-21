"""Poster figures for the R1 "Failure -> fix" panel (plan section 6, panel 6).

One message: the retriever missed a table, so QueryMind refused answerable
questions; we fixed it. Writes three vector PDFs with the shared poster style:

* `r1_over_refusal.pdf`    - refused / answerable for Neo4j and flat mode, before vs after.
* `r1_e3_before_after.pdf` - question E3 as a before card and an after card (trace text).
* `r1_schema_graph.pdf`    - the stakeholder schema as the graph Neo4j stores, with the
  E3 seed table and its one-hop foreign-key neighbour highlighted.

Every number and string comes from the trace, question and database files read here.
When the "after" traces are missing, the figures say "pending" in their place.

    .venv/bin/python -m scripts.make_r1_figures [--after-dir eval/results/report/poster-freeze/...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections.abc import Iterable, Mapping
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle  # noqa: E402

from scripts.poster_style import (  # noqa: E402
    BODY_PT, GRID, LABEL_PT, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, apply_style, arm_color, figure, save,
)
from src.schema.build_graph import build_schema_graph  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BEFORE_DIR = PROJECT_ROOT / "eval/results/report/stakeholder/r1"
QUESTIONS = PROJECT_ROOT / "external/agentic-sql-analyst/eval/questions.yaml"
DB_PATH = PROJECT_ROOT / "data/stakeholder_analytics.db"
OUT_DIR = PROJECT_ROOT / "eval/results/poster"

ANSWERABLE = ("reference", "ambiguous")  # same rule as scripts/score_report_eval.py over_refusal
MODES = (("querymind", "Neo4j mode"), ("querymind-flat", "Flat mode"))
E3 = "E3"
E3_SEED = "customers"  # the one table Neo4j mode retrieved for E3 before the fix
PENDING = "pending"
LINE_IN = LABEL_PT * 1.4 / 72  # one text line at LABEL_PT, in inches


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_kinds(path: Path) -> dict[str, str]:
    return {q["id"]: q["kind"] for q in yaml.safe_load(path.read_text(encoding="utf-8"))}


def over_refusal(records: Iterable[Mapping], kinds: Mapping[str, str] | Iterable[Mapping]) -> tuple[int, int]:
    """Return (refused, answerable) over the answerable questions in `kinds`.

    `kinds` is {question_id: kind} or a list of {"id", "kind"} dicts. As in
    score_report_eval.py, n counts every answerable question; one with no trace
    record counts as not refused.
    """
    if not isinstance(kinds, Mapping):
        kinds = {q["id"]: q["kind"] for q in kinds}
    answerable = {qid for qid, kind in kinds.items() if kind in ANSWERABLE}
    refused = {r["question_id"] for r in records if r.get("question_id") in answerable and r.get("refused")}
    return len(refused), len(answerable)


def record_for(records: Iterable[Mapping], question_id: str) -> Mapping | None:
    return next((r for r in records if r.get("question_id") == question_id), None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def lighten(color: str, amount: float = 0.6) -> tuple[float, float, float]:
    r, g, b = to_rgb(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


def wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(" ".join(str(text).split()), width=width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return lines


def inch_axes(fig):
    """Turn the figure's axes into a blank canvas whose data units are inches."""
    fig.set_layout_engine("none")
    ax = fig.axes[0]
    ax.set_position([0, 0, 1, 1])
    w, h = fig.get_size_inches()
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return ax, w, h


# --------------------------------------------------------------------------- #
# Figure 1: over-refusal before vs after
# --------------------------------------------------------------------------- #

def fig_over_refusal(before: dict[str, list[dict]], after: dict[str, list[dict]] | None,
                     kinds: dict[str, str], out: Path) -> tuple[Path, dict]:
    fig, ax = figure("half")
    width = 0.38
    numbers: dict = {}
    for i, (arm, mode_label) in enumerate(MODES):
        color = arm_color(arm)
        phases = (("before", before.get(arm) or []), ("after", (after or {}).get(arm) or []))
        for j, (phase, records) in enumerate(phases):
            x = i + (j - 0.5) * width
            if not records:
                numbers[f"{arm}/{phase}"] = PENDING
                ax.bar(x, 1.0, width * 0.92, fill=False, edgecolor=GRID, linewidth=2, linestyle="--")
                ax.text(x, 0.5, PENDING, ha="center", va="center", rotation=90,
                        fontsize=LABEL_PT, color=TEXT_SECONDARY)
                continue
            k, n = over_refusal(records, kinds)
            numbers[f"{arm}/{phase}"] = [k, n]
            rate = k / n if n else 0.0
            if phase == "before":
                ax.bar(x, rate, width * 0.92, color=lighten(color), edgecolor=color, linewidth=2, hatch="//")
            else:
                ax.bar(x, rate, width * 0.92, color=color, edgecolor=color, linewidth=2)
            ax.text(x, rate + 0.02, f"{k}/{n}\n{rate:.0%}", ha="center", va="bottom",
                    fontsize=LABEL_PT, color=TEXT_PRIMARY, linespacing=1.1)
    ax.set_xticks(range(len(MODES)), [label for _, label in MODES])
    ax.set_xlim(-0.6, len(MODES) - 0.4)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("Answerable questions refused")
    ax.set_title("Refusals on answerable questions")
    ax.tick_params(axis="x", length=0)
    neutral = TEXT_SECONDARY
    ax.legend(handles=[Patch(facecolor=lighten(neutral), edgecolor=neutral, hatch="//", label="Before fix"),
                       Patch(facecolor=neutral, edgecolor=neutral, label="After fix")],
              loc="upper center", bbox_to_anchor=(0.5, -0.1), ncols=2, handlelength=1.4, columnspacing=1.5)
    return save(fig, out / "r1_over_refusal"), numbers


# --------------------------------------------------------------------------- #
# Figure 2: E3 before / after cards
# --------------------------------------------------------------------------- #

CHAR_IN = 0.17       # average DejaVu Sans advance at LABEL_PT, inches
MONO_CHAR_IN = 0.205  # DejaVu Sans Mono advance at LABEL_PT, inches


def _card(ax, x0, y_top, w, title, title_color, rows):
    """Draw a card at y_top and return its bottom edge.

    rows: (label, text, mono, max_lines); labels sit in a left column, values wrap beside them.
    """
    pad, label_w = 0.25, 1.75
    value_w = w - 2 * pad - label_w
    h = (1 + sum(len(wrap(t, int(value_w / (MONO_CHAR_IN if m else CHAR_IN)), n)) for _, t, m, n in rows)) \
        * LINE_IN + 2 * pad
    ax.add_patch(FancyBboxPatch((x0, y_top - h), w, h, boxstyle="round,pad=0,rounding_size=0.15",
                                facecolor="white", edgecolor=title_color, linewidth=3))
    y = y_top - pad - LINE_IN / 2
    ax.text(x0 + pad, y, title, va="center", fontsize=LABEL_PT, fontweight="bold", color=title_color)
    for label, text, mono, max_lines in rows:
        y -= LINE_IN
        ax.text(x0 + pad, y, label, va="center", fontsize=LABEL_PT, fontweight="bold", color=TEXT_SECONDARY)
        lines = wrap(text, int(value_w / (MONO_CHAR_IN if mono else CHAR_IN)), max_lines)
        for n, line in enumerate(lines):
            ax.text(x0 + pad + label_w, y, line, va="center", fontsize=LABEL_PT, color=TEXT_PRIMARY,
                    family="DejaVu Sans Mono" if mono else None, parse_math=False)
            if n < len(lines) - 1:
                y -= LINE_IN
    return y_top - h


def fig_e3(before_rec: Mapping | None, after_rec: Mapping | None, out: Path) -> tuple[Path, dict]:
    fig, _ = figure("half")
    ax, w, h = inch_axes(fig)
    margin = 0.3
    question = (before_rec or after_rec or {}).get("question", PENDING)
    ax.text(margin, h - 0.45, f"E3: “{question}”", fontsize=BODY_PT, fontweight="bold",
            va="center", ha="left", color=TEXT_PRIMARY, parse_math=False)

    def tables(rec):
        return ", ".join(rec.get("qm_retrieved_tables") or []) if rec else PENDING

    def sql(rec):
        return re.sub(r"\s+", " ", rec.get("sql") or "").strip().rstrip(";") if rec else PENDING

    def answer(rec):
        return "; ".join(s.strip() for s in (rec or {}).get("qm_final_answer", "").splitlines() if s.strip()) \
            or PENDING

    def outcome(rec):
        return "" if rec is None else (": refused" if rec.get("refused") else ": answered")

    bottom = _card(ax, margin, h - 0.95, w - 2 * margin, f"Before the fix{outcome(before_rec)}", TEXT_SECONDARY, [
        ("Tables:", tables(before_rec), False, 1),
        ("Answer:", answer(before_rec), False, 2),
    ])
    _card(ax, margin, bottom - 0.3, w - 2 * margin, f"After the fix{outcome(after_rec)}", arm_color("querymind"), [
        ("Tables:", tables(after_rec), False, 1),
        ("SQL:", sql(after_rec), True, 3),
        ("Answer:", answer(after_rec), False, 2),
    ])
    before_answer, after_answer = answer(before_rec), answer(after_rec)
    numbers = {"before_tables": tables(before_rec), "before_answer": before_answer,
               "after_tables": tables(after_rec), "after_sql": sql(after_rec), "after_answer": after_answer}
    return save(fig, out / "r1_e3_before_after"), numbers


# --------------------------------------------------------------------------- #
# Figure 3: schema graph
# --------------------------------------------------------------------------- #

def fig_schema_graph(db_path: Path, out: Path) -> tuple[Path, dict]:
    graph = build_schema_graph(db_path)
    tables = {t["name"]: [c["name"] for c in sorted(t["columns"], key=lambda c: c["position"])]
              for t in graph["tables"]}
    fks = [(r["from_table"], r["from_column"], r["to_table"], r["to_column"]) for r in graph["relationships"]]
    neighbours = {f for f, _, t, _ in fks if t == E3_SEED} | {t for f, _, t, _ in fks if f == E3_SEED}
    highlighted = {E3_SEED} | neighbours

    # Tables that reference others sit on the left; the tables they point at stack on the right.
    sources = sorted({f for f, *_ in fks})
    targets = sorted(set(tables) - set(sources))

    fig, _ = figure("half")
    ax, w, h = inch_axes(fig)
    blue = arm_color("querymind")
    row, pad = LINE_IN, 0.12
    renderer = fig.canvas.get_renderer()
    widths = []
    for name, cols in tables.items():
        for text, weight in ((name, "bold"), *((c, "normal") for c in cols)):
            probe = ax.text(0, 0, text, fontsize=LABEL_PT, fontweight=weight)
            widths.append(probe.get_window_extent(renderer).width / fig.dpi)
            probe.remove()
    box_w = max(widths) + 0.35  # 0.2 left inset + 0.15 right
    rows_at: dict[tuple[str, str], tuple[float, float, float]] = {}  # (table, col) -> (x_left, x_right, y)

    def draw_table(name, x0, y_top):
        cols = tables[name]
        hi = name in highlighted
        edge = blue if hi else TEXT_SECONDARY
        height = (len(cols) + 1) * row + 2 * pad
        ax.add_patch(Rectangle((x0, y_top - height), box_w, height, facecolor=lighten(blue, 0.85) if hi else "white",
                               edgecolor=edge, linewidth=4 if hi else 2))
        ax.add_patch(Rectangle((x0, y_top - row - pad), box_w, row + pad, facecolor=edge, edgecolor=edge,
                               linewidth=4 if hi else 2))
        ax.text(x0 + 0.15, y_top - (row + pad) / 2, name, color="white", fontweight="bold",
                fontsize=LABEL_PT, va="center")
        y = y_top - row - pad - pad - row / 2
        for col in cols:
            ax.text(x0 + 0.2, y, col, fontsize=LABEL_PT, va="center", color=TEXT_PRIMARY)
            rows_at[(name, col)] = (x0, x0 + box_w, y)
            y -= row
        return y_top - height

    def tag(name, x0, y_top):
        if name in highlighted:
            ax.text(x0, y_top + 0.08, "E3 seed" if name == E3_SEED else "one-hop neighbour", fontsize=LABEL_PT,
                    fontweight="bold", color=blue, va="bottom")

    top = h - 1.4
    y = top
    for name in sources:
        tag(name, 0.2, y)
        y = draw_table(name, 0.2, y) - 0.6
    left_bottom = y
    y = top
    for name in targets:
        tag(name, w - 0.2 - box_w, y)
        y = draw_table(name, w - 0.2 - box_w, y) - 0.6

    for f, fc, t, tc in fks:
        _, x_from, y_from = rows_at[(f, fc)]
        x_to, _, y_to = rows_at[(t, tc)]
        hi = f in highlighted and t in highlighted
        color = blue if hi else TEXT_SECONDARY
        ax.add_patch(FancyArrowPatch((x_from, y_from), (x_to, y_to), arrowstyle="-|>", mutation_scale=30,
                                     color=color, linewidth=3.5 if hi else 2.5, shrinkA=0, shrinkB=4))
        mx, my = (x_from + x_to) / 2, (y_from + y_to) / 2
        label = f"{f}.{fc} →\n{t}.{tc}"
        if abs(y_to - y_from) < 2 * row:  # near-horizontal arrow: label above it so the arrow stays visible
            ax.text(mx, max(y_from, y_to) + 0.12, label, fontsize=LABEL_PT, ha="center", va="bottom",
                    color=color, linespacing=1.1)
        else:  # long diagonal arrow: label on it, the arrow shows on both sides
            ax.text(mx, my, label, fontsize=LABEL_PT, ha="center", va="center", color=color, linespacing=1.1,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=SURFACE, edgecolor="none"))

    ax.text(0.3, h - 0.45, "The schema graph Neo4j stores", fontsize=BODY_PT, fontweight="bold",
            va="center", color=TEXT_PRIMARY)
    # Legend under the left column: name the graph pieces, then the highlight.
    legend = [("Table", "box header"), ("Column", "row in a box"),
              ("HAS_COLUMN", "box lists its rows"), ("REFERENCES", "foreign-key arrow")]
    term_w = max(len(term) for term, _ in legend) * MONO_CHAR_IN + 0.2
    yy = left_bottom - 0.1
    for term, meaning in legend:
        ax.text(0.3, yy, term, fontsize=LABEL_PT, fontweight="bold", va="center", color=TEXT_PRIMARY,
                family="DejaVu Sans Mono")
        ax.text(0.3 + term_w, yy, f"= {meaning}", fontsize=LABEL_PT, va="center", color=TEXT_SECONDARY)
        yy -= row
    ax.add_patch(Rectangle((0.3, yy - 0.15), 0.3, 0.3, facecolor=lighten(blue, 0.85), edgecolor=blue, linewidth=3))
    ax.text(0.75, yy, "= retrieved for E3 after the fix", fontsize=LABEL_PT, va="center", color=blue)
    numbers = {"tables": tables, "references": [f"{f}.{fc} -> {t}.{tc}" for f, fc, t, tc in fks],
               "highlighted": sorted(highlighted)}
    return save(fig, out / "r1_schema_graph"), numbers


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def load_runs(directory: Path | None) -> dict[str, list[dict]] | None:
    if directory is None:
        return None
    runs = {arm: load_records(Path(directory) / f"{arm}__main.jsonl") for arm, _ in MODES}
    return runs if any(runs.values()) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before-dir", type=Path, default=BEFORE_DIR)
    parser.add_argument("--after-dir", type=Path, default=None)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    apply_style()
    kinds = load_kinds(args.questions)
    before = load_runs(args.before_dir) or {}
    after = load_runs(args.after_dir)
    if args.after_dir is not None and after is None:
        print(f"no after traces in {args.after_dir}; rendering 'after' as pending", file=sys.stderr)

    results = {
        "over_refusal": fig_over_refusal(before, after, kinds, args.out),
        "e3": fig_e3(record_for(before.get("querymind", []), E3),
                     record_for((after or {}).get("querymind", []), E3), args.out),
        "schema_graph": fig_schema_graph(args.db, args.out),
    }
    for name, (path, numbers) in results.items():
        print(f"{name}: {path}")
        print("  " + json.dumps(numbers, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
