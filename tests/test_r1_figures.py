"""R1 "Failure -> fix" poster figures (scripts/make_r1_figures.py)."""

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("scripts.poster_style")

from scripts.make_r1_figures import main as make_figures, over_refusal  # noqa: E402


def test_over_refusal_counts_refused_answerable_questions():
    kinds = [{"id": "A", "kind": "reference"}, {"id": "B", "kind": "ambiguous"},
             {"id": "C", "kind": "reference"}, {"id": "D", "kind": "unanswerable"}]
    records = [
        {"question_id": "A", "refused": True},
        {"question_id": "B", "refused": False},
        {"question_id": "D", "refused": True},  # unanswerable: a refusal here is correct, not over-refusal
        # C has no record: still answerable (n), not refused (k), as in score_report_eval.py
    ]
    assert over_refusal(records, kinds) == (1, 3)
    assert over_refusal(records, {q["id"]: q["kind"] for q in kinds}) == (1, 3)
    assert over_refusal([], kinds) == (0, 3)


def test_script_writes_three_pdfs(tmp_path):
    assert make_figures(["--out", str(tmp_path), "--after-dir", str(tmp_path / "missing")]) == 0
    assert sorted(p.name for p in tmp_path.glob("*.pdf")) == [
        "r1_e3_before_after.pdf", "r1_over_refusal.pdf", "r1_schema_graph.pdf"]
