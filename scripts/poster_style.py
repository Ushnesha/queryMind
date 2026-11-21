"""Shared look for every poster figure (24 x 36 in portrait poster).

Every member's figure script imports this module so that fonts, colours and
sizes match across panels:

    from scripts.poster_style import apply_style, arm_color, figure, save

    apply_style()
    fig, ax = figure("half")
    ax.bar(..., color=arm_color("querymind"))
    save(fig, "eval/results/poster/my_panel")   # writes my_panel.pdf (vector)

Sizes are in inches at final print size, so a 24 pt label here is 24 pt on the
printed poster; do not rescale figures when placing them in the poster.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

# --- Type sizes (pt at final print size; plan section 6) -------------------
TITLE_PT = 90           # poster title (set in the poster layout, not in figures)
HEADING_PT = 48         # panel headings (poster layout)
BODY_PT = 28            # body text, figure titles
LABEL_PT = 24           # axis labels, tick labels, legends, value labels (minimum)
FONT_FAMILY = ["DejaVu Sans"]  # ships with matplotlib, so every member renders identically

# --- Surfaces and ink -------------------------------------------------------
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
TARGET_LINE = "#0b0b0b"

# --- Systems (fixed colour per arm, never reassigned by rank) ---------------
# Order b0, b1, b2, QueryMind, QueryMind-flat was validated as adjacent bars with
# the dataviz palette validator (light mode): CVD dE >= 9.2, normal-vision
# dE >= 24. Three slots sit under 3:1 contrast on the surface, so bars always
# carry direct value labels.
ARMS = ("b0", "b1", "b2", "querymind", "querymind-flat")
ARM_COLORS = {
    "b0": "#6250d6",              # violet
    "b1": "#eb6834",              # orange
    "b2": "#1baf7a",              # aqua
    "querymind": "#2a78d6",       # blue
    "querymind-flat": "#e87ba4",  # magenta
}
ARM_LABELS = {
    "b0": "b0",
    "b1": "b1",
    "b2": "b2 (k=3 vote)",
    "querymind": "QueryMind",
    "querymind-flat": "QueryMind (flat)",
}
# Extra categorical slots for non-arm series (e.g. before/after, per-agent),
# continuing the same validated order.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
BEFORE_AFTER = {"before": "#8a8984", "after": "#2a78d6"}

# --- Figure sizes (inches, final print size) --------------------------------
# The poster is 24 in wide; panels are full width or half width with margins.
SIZES = {
    "full": (22.0, 9.0),
    "half": (10.8, 8.0),
    "half-tall": (10.8, 11.0),
    "third": (7.0, 6.5),
}


def apply_style() -> None:
    """Set matplotlib defaults for poster figures. Call once per script."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONT_FAMILY,
        "font.size": LABEL_PT,
        "axes.titlesize": BODY_PT,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelsize": LABEL_PT,
        "axes.labelcolor": TEXT_SECONDARY,
        "axes.edgecolor": GRID,
        "axes.linewidth": 1.5,
        "axes.facecolor": SURFACE,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 1.0,
        "xtick.labelsize": LABEL_PT,
        "ytick.labelsize": LABEL_PT,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "legend.fontsize": LABEL_PT,
        "legend.frameon": False,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "lines.linewidth": 3.0,
        "lines.markersize": 12,
        "text.color": TEXT_PRIMARY,
        "pdf.fonttype": 42,   # embed TrueType so `pdffonts` shows embedded fonts
        "ps.fonttype": 42,
    })


def arm_color(arm: str) -> str:
    return ARM_COLORS[arm]


def arm_label(arm: str) -> str:
    return ARM_LABELS.get(arm, arm)


def figure(size: str = "half", **kwargs):
    """Return (fig, ax) at a named poster size; kwargs go to plt.subplots."""
    return plt.subplots(figsize=SIZES[size], layout="constrained", **kwargs)


def save(fig, path: str | Path) -> Path:
    """Save a vector PDF (and a PNG preview) and close the figure."""
    path = Path(path).with_suffix(".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    fig.savefig(path.with_suffix(".png"), dpi=72)
    plt.close(fig)
    return path
