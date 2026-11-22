"""Hand-made rows only: no scorer, no traces on disk."""

from scripts.analyze_verifiers import CHECKS, analyze, check_rates, rate, semantic_pairs, wilson


def row(kind, correct, **record):
    return {"kind": kind, "correct": correct, "record": record}


def test_wilson_matches_stakeholder_example():
    low, high = wilson(5, 5)
    assert round(low) == 57 and round(high) == 100  # stakeholder report shows "5/5 CI 57-100"


def test_rate_flags_small_and_empty_samples():
    assert rate(3, 4)["too_few"] is True
    assert rate(5, 10)["too_few"] is False
    assert rate(0, 0)["pct"] is None


def test_mismatch_uses_repairs_and_reference_questions_only():
    rows = [
        row("reference", False, qm_repair_count=1),   # flagged, wrong: TP
        row("reference", True, qm_repair_count=1),    # flagged, right: FP
        row("reference", False, qm_repair_count=0),   # not flagged, wrong: FN
        row("reference", True, qm_repair_count=0),    # TN
        row("unanswerable", False, qm_repair_count=1),  # ignored: not a reference question
    ]
    m = analyze(rows)["semantic"]["mismatch"]
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"]["k"] == 1 and m["precision"]["n"] == 2


def test_not_answerable_needs_refusal_and_named_field():
    rows = [
        row("unanswerable", True, refused=True, missing_field="churn"),   # TP
        row("unanswerable", False, refused=False),                         # FN (fabricated)
        row("reference", False, refused=True, missing_field="x"),          # FP (over-refusal)
        row("reference", True, refused=False),                             # TN
    ]
    m = analyze(rows)["semantic"]["not_answerable"]
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)


def test_assumption_flag_ignores_blank_text_and_unscored_rows():
    rows = [
        row("ambiguous", True, assumptions="Assumed revenue = SUM(amount)"),  # TP
        row("reference", True, assumptions="   "),                            # TN (blank)
        row("ambiguous", None, assumptions="x"),                              # unscored: dropped
    ]
    pairs = semantic_pairs(rows)["assumption_flagged"]
    assert pairs == [(True, True), (False, False)]


def test_check_rates_split_by_scorer_verdict_and_skip_unexecuted():
    rows = [
        row("reference", True, exec_ok=True, qm_result_warnings=[]),
        row("reference", False, exec_ok=True, qm_result_warnings=["EMPTY_RESULT: none", "DUPLICATE_ROWS: 2"]),
        row("reference", False, exec_ok=True, qm_result_warnings=["EMPTY_RESULT: none"]),
        row("reference", False, exec_ok=False, qm_result_warnings=["EMPTY_RESULT: ignored"]),  # never executed
    ]
    out = {c["check"]: c for c in check_rates(rows)}
    assert len(out) == len(CHECKS) == 14
    assert (out["EMPTY_RESULT"]["on_correct"]["k"], out["EMPTY_RESULT"]["on_correct"]["n"]) == (0, 1)
    assert (out["EMPTY_RESULT"]["on_wrong"]["k"], out["EMPTY_RESULT"]["on_wrong"]["n"]) == (2, 2)
    assert out["DUPLICATE_ROWS"]["on_wrong"]["k"] == 1
