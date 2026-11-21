"""Poster strip "Example interactions": three cards built from real trace records.

    python scripts/make_example_cards.py --traces eval/results/report --repeat r1 \
        --db data/stakeholder_analytics.db --out eval/results/poster/example_interactions.pdf

Each card shows the question, the SQL, a short answer and the assumption or refusal, exactly as
recorded in the trace. Text is wrapped and the answer is cropped with "..." when long, but no
word of the question, SQL or answer is ever rewritten. The b0 contrast line is the result of
running b0's own recorded SQL, read only, against the demo database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
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
    from scripts.poster_style import ARM_COLORS, BODY_PT, LABEL_PT, TEXT_PRIMARY, TEXT_SECONDARY, apply_style, figure, save
    ACCENT, WARN = ARM_COLORS["querymind"], ARM_COLORS["b1"]
except ImportError:  # stand-in with the same minimum sizes, replaced by the real module once merged
    BODY_PT, LABEL_PT, TEXT_PRIMARY, TEXT_SECONDARY = 28, 24, "#0b0b0b", "#52514e"
    ACCENT, WARN = "#2a78d6", "#eb6834"

    def apply_style() -> None:
        plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "pdf.fonttype": 42})

    def figure(size: str = "full"):
        return plt.subplots(figsize=(22.0, 9.0), layout="constrained")

    def save(fig, path):
        path = Path(path).with_suffix(".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        return path

# (trace question id, the question as the poster plan words it)
CARDS = (
    ("A1", "Who are our most active customers?"),
    ("H3", "What is the profit margin per category?"),
    ("H1", "Show sales trends over time"),
)
ANSWER_CHARS = 120
CARD_W = 7.0


def read_record(traces: Path, repeat: str, arm: str, qid: str) -> dict:
    path = traces / "stakeholder" / repeat / f"{arm}__main.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["question_id"] == qid:
            return json.loads(line)
    raise KeyError(f"{qid} not found in {path}")


def same_question(a: str, b: str) -> bool:
    clean = lambda s: s.lower().strip().rstrip(".?!")  # noqa: E731
    return clean(a) == clean(b)


def crop(text: str, limit: int = ANSWER_CHARS) -> str:
    """First `limit` characters on word boundaries, '...' when cut; never rewords."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def card_from_record(rec: dict) -> dict:
    """The fields a card shows, taken straight from a QueryMind trace record."""
    refused = bool(rec.get("refused"))
    return {
        "question": rec["question"],
        "tag": "Refused: data is missing" if refused else "Assumption stated",
        "sql": None if refused else rec["sql"],
        "answer": crop(rec["qm_reason"] if refused else rec["qm_final_answer"]),
        "rows": rec.get("rows"),
        "note": None if refused else rec["assumptions"],
        "refused": refused,
    }


def b0_contrast(rec: dict, db_path: Path) -> str | None:
    """Run b0's recorded SQL read only and describe what it returned (None if impossible)."""
    if not rec.get("sql") or not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(rec["sql"]).fetchall()
    finally:
        conn.close()
    return "; ".join(f"{name} {value:.1f}%" for name, value in rows)


def wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for part in text.splitlines() or [""]:
        out += textwrap.wrap(part, width, break_long_words=True) or [""]
    return out


def put(ax, x: float, y: float, lines: list[str], pt: float, **kw) -> float:
    """Draw lines top-anchored at y (skip drawing when ax is None); return the y below them."""
    if ax is not None:
        ax.text(x, y, "\n".join(lines), fontsize=pt, va="top", linespacing=1.25, **kw)
    return y - len(lines) * pt * 1.25 / 72 - 0.06


def draw_card(ax, x: float, card: dict, top: float, contrast: str | None, color: str | None = None,
              box: tuple[float, float] | None = None) -> float:
    """Lay out one card downward from `top`; return its bottom y. ax=None only measures."""
    color = color or (WARN if card["refused"] else ACCENT)
    if ax is not None and box:
        ax.add_patch(FancyBboxPatch((x, box[0]), CARD_W, box[1], boxstyle="round,pad=0.02,rounding_size=0.15",
                                    fc=to_rgba(color, 0.08), ec=color, lw=2))
    left, y = x + 0.25, top - 0.2
    y = put(ax, left, y, [card["tag"]], LABEL_PT, weight="bold", color=color) - 0.1
    y = put(ax, left, y, wrap(card["question"], 27), BODY_PT, weight="bold", color=TEXT_PRIMARY) - 0.15
    y = put(ax, left, y, ["SQL"], LABEL_PT, weight="bold", color=TEXT_SECONDARY)
    sql = ["No SQL: it refused."] if card["sql"] is None else wrap(card["sql"], 31)
    y = put(ax, left, y, sql, LABEL_PT, color=TEXT_PRIMARY, family="DejaVu Sans Mono") - 0.1
    label = "Answer" if card["rows"] is None else f"Answer ({card['rows']} rows)"
    y = put(ax, left, y, [label], LABEL_PT, weight="bold", color=TEXT_SECONDARY)
    y = put(ax, left, y, wrap(card["answer"], 34), LABEL_PT, color=TEXT_PRIMARY) - 0.1
    if card["note"]:
        y = put(ax, left, y, ["Assumption it stated"], LABEL_PT, weight="bold", color=TEXT_SECONDARY)
        y = put(ax, left, y, wrap(card["note"], 34), LABEL_PT, color=TEXT_PRIMARY) - 0.1
    if contrast:
        y = put(ax, left, y, ["b0 answered anyway"], LABEL_PT, weight="bold", color=WARN)
        y = put(ax, left, y, wrap(contrast, 34), LABEL_PT, color=TEXT_PRIMARY)
    return y - 0.2


def make_strip(cards: list[dict], contrasts: list[str | None], out: Path) -> Path:
    """Three equal-height cards; the strip is as tall as the longest card needs (at least 9 in)."""
    height = max(9.0, max(-draw_card(None, 0, c, 0, k) for c, k in zip(cards, contrasts)))
    apply_style()
    if height > 9.0:  # the shared "full" size is 22 x 9; grow only when the text needs it
        fig, ax = plt.subplots(figsize=(22.0, height), layout="constrained")
    else:
        fig, ax = figure("full")
    ax.set_xlim(0, 22)
    ax.set_ylim(0, height)
    ax.axis("off")
    for i, (card, contrast) in enumerate(zip(cards, contrasts)):
        draw_card(ax, 0.1 + i * (CARD_W + 0.3), card, height - 0.1, contrast, box=(0.1, height - 0.2))
    return save(fig, out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--traces", type=Path, default=PROJECT_ROOT / "eval/results/report")
    parser.add_argument("--repeat", default="r1")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data/stakeholder_analytics.db")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval/results/poster/example_interactions.pdf")
    args = parser.parse_args(argv)

    cards, contrasts = [], []
    for qid, wanted in CARDS:
        rec = read_record(args.traces, args.repeat, "querymind", qid)
        if not same_question(rec["question"], wanted):
            parser.error(f"{qid} is {rec['question']!r}, not {wanted!r}: question ids changed")
        cards.append(card_from_record(rec))
        contrasts.append(b0_contrast(read_record(args.traces, args.repeat, "b0", qid), args.db)
                         if cards[-1]["refused"] else None)
    print(f"wrote {make_strip(cards, contrasts, args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
