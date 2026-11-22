from scripts.make_verifier_figures import fmt_rate, make_panel


def rate(k, n, pct=None, too_few=False):
    return {"k": k, "n": n, "pct": pct, "ci_low": 0, "ci_high": 0, "too_few": too_few}


def test_fmt_rate_shows_counts_and_star_for_small_samples():
    assert fmt_rate(rate(6, 21, 28.57)) == "29%  (6/21)"
    assert fmt_rate(rate(0, 1, 0.0, True)) == "0%  (0/1)*"
    assert fmt_rate(rate(0, 0)) == "n/a (0)"


def test_panel_writes_a_pdf(tmp_path):
    verdict = {"precision": rate(6, 21, 28.6), "recall": rate(6, 6, 100.0)}
    analysis = {"semantic": {k: verdict for k in ("mismatch", "not_answerable", "assumption_flagged")}}
    out = tmp_path / "panel.pdf"
    make_panel(analysis, out)
    assert out.read_bytes().startswith(b"%PDF")
