"""b2 trace records, the shared poster style, and Member 1's poster panels."""

import json
from pathlib import Path

from scripts.make_poster_figures import main as make_figures, wilson
from scripts.poster_style import ARM_COLORS, ARM_LABELS, ARMS
from scripts.run_b2_trace import b2_record
from src.evaluation.b2 import run_self_consistency


class SequenceProvider:
    is_mock = True

    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def generate(self, question, schema_context):
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


def _record(outputs, db_path):
    provider = SequenceProvider(outputs)
    report = run_self_consistency("IDs", db_path=db_path, provider=provider)
    return b2_record("Q1", "IDs", report, provider, model="m", provider_name="opencode",
                     temperature=0.7, run_tag="r1")


def test_b2_majority_is_an_executed_answer(db_path: Path):
    record = _record(["SELECT customer_id FROM customers"] * 2 + ["SELECT 1"], db_path)
    assert record["arm"] == "b2" and record["prompt_version"] == "b2-k3"
    assert record["exec_ok"] is True and record["refused"] is False
    assert record["b2_majority_count"] == 2 and record["b2_selected_index"] == 0
    assert record["sql"] == "SELECT customer_id FROM customers"
    assert record["temperature"] == 0.7


def test_b2_without_majority_is_an_abstention(db_path: Path):
    record = _record([f"SELECT {n} AS n" for n in (1, 2, 3)], db_path)
    assert record["exec_ok"] is False and record["refused"] is True
    assert record["missing_field"] is None and record["error_type"] is None


def test_b2_refusal_consensus_names_the_missing_field(db_path: Path):
    record = _record(["NOT_ANSWERABLE: product cost"] * 3, db_path)
    assert record["refused"] is True and record["missing_field"] == "product cost"


def test_b2_gateway_failure_is_infrastructure_not_refusal(db_path: Path):
    error = ValueError("Provider network error: timed out")
    record = _record(["SELECT 1 AS n", error, error], db_path)
    assert record["refused"] is False and record["error_type"] == "ProviderError"


def test_every_arm_has_a_style():
    assert set(ARMS) == set(ARM_COLORS) == set(ARM_LABELS)
    assert len(set(ARM_COLORS.values())) == len(ARMS)


def test_wilson_matches_known_interval():
    low, high = wilson(2, 5)
    assert round(100 * low) == 12 and round(100 * high) == 77


def _summary(n_answerable=11):
    def arm(easy, hard, unans, fab, amb, over, exec_ok, lat):
        return {"set_easy": [easy, 5], "set_hard": [hard, 5], "unanswerable_refused_correctly": [unans, 6],
                "fabrications": [fab, 6], "ambiguity_flagged": [amb, 4], "over_refusal": [over, n_answerable],
                "exec_success": [exec_ok, 17], "latency_answered_s": {"p50": lat, "p95": lat * 2, "n": 5},
                "llm_calls_per_question": 1.0 if lat < 5 else 2.0, "tokens_per_question": 300.0}
    summaries = {"r1": {"b0": arm(5, 0, 0, 5, 0, 0, 15, 3.8), "b1": arm(5, 1, 6, 0, 0, 2, 9, 3.3),
                        "b2": arm(5, 2, 6, 0, 0, 3, 8, 9.0), "querymind": arm(4, 3, 6, 0, 3, 3, 8, 11.0)}}
    paired = {"b0 vs b1": {"n": 17, "a_only": 0, "b_only": 6, "p_exact_mcnemar": 0.03},
              "b2 vs b1": {"n": 17, "a_only": 1, "b_only": 0, "p_exact_mcnemar": 1.0},
              "querymind vs b1": {"n": 17, "a_only": 4, "b_only": 1, "p_exact_mcnemar": 0.38}}
    return {"manifest": {"runs": []},
            "datasets": {"stakeholder": {"summaries": summaries, "paired_r1": paired}}}


def test_poster_panels_are_written(tmp_path: Path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(_summary()))
    out = tmp_path / "poster"
    assert make_figures(["--summary", str(summary), "--out", str(out)]) == 0
    for name in ("results_table.pdf", "results_table.tex", "results_table.md", "metrics_vs_targets.pdf",
                 "honest_results.md", "honest_results.tex", "poster_numbers.json"):
        assert (out / name).stat().st_size > 0, name
    numbers = json.loads((out / "poster_numbers.json").read_text())
    assert numbers["dataset"] == "stakeholder"  # falls back to the 17-question set
    assert numbers["arms"] == ["b0", "b1", "b2", "querymind"]
    honest = numbers["honest_results"]
    assert any(item.startswith("Hard accuracy") for item in honest["better"])
    assert any(item.startswith("Easy accuracy") for item in honest["worse"])
    assert "2.0× the LLM calls" in " ".join(honest["cost"])
    table = (out / "results_table.md").read_text()
    assert "+4 / −1, p=0.38" in table and "ref." in table
