import pytest

from scripts.annotation_agreement import agreement, load_labels


def test_perfect_agreement_gives_kappa_one():
    a = {"q1": "measure", "q2": "time", "q3": "measure", "q4": "time"}
    out = agreement(a, dict(a))
    assert out["raw_agreement"]["k"] == 4 and out["kappa"] == pytest.approx(1.0)


def test_known_kappa_value():
    # 10 items. Both say "yes" on 4 and "no" on 3; A says yes / B says no on 2; A no / B yes on 1.
    a = {f"q{i}": "yes" for i in range(6)} | {f"q{i}": "no" for i in range(6, 10)}
    b = {f"q{i}": "yes" for i in range(4)} | {"q4": "no", "q5": "no", "q6": "yes"} | {f"q{i}": "no" for i in range(7, 10)}
    out = agreement(a, b)
    # observed 7/10; chance = 0.6*0.5 + 0.4*0.5 = 0.5; kappa = (0.7 - 0.5) / 0.5 = 0.4
    assert out["raw_agreement"]["k"] == 7 and out["kappa"] == pytest.approx(0.4)
    assert out["disagreements"] == ["q4", "q5", "q6"]


def test_kappa_undefined_when_everyone_uses_one_label():
    out = agreement({"q1": "x", "q2": "x"}, {"q1": "x", "q2": "x"})
    assert out["kappa"] is None and out["raw_agreement"]["k"] == 2


def test_only_shared_ids_are_compared_and_missing_ones_reported():
    out = agreement({"q1": "a", "q2": "b"}, {"q2": "b", "q3": "c"})
    assert out["n"] == 1 and out["only_in_first_file"] == ["q1"] and out["only_in_second_file"] == ["q3"]


def test_no_overlap_fails_loudly():
    with pytest.raises(ValueError):
        agreement({"q1": "a"}, {"q2": "a"})


def test_empty_labels_are_skipped_when_loading(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("- {id: q1, label: time}\n- {id: q2, label: null}\n- {id: q3}\n", encoding="utf-8")
    assert load_labels(path, "label") == {"q1": "time"}
