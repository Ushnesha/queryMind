"""Member 3 analysis and poster scripts on synthetic records (no gateway, no stakeholder venv)."""

import json
import math

import pytest

from scripts.analyze_latency import compare
from scripts.make_member3_figures import main as make_figures
from scripts.run_live_ablation import main as run_live_ablation, variant_cli
from scripts.score_ablation import ablation_table, markdown, mcnemar_exact, newcombe
from src.evaluation.ablation import experiment_variants


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Same formula as the stakeholder's score.wilson (percentages)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half) * 100, min(1.0, centre + half) * 100)


def _record(qid, latency_ms, *, exec_ok=True, refused=False, nodes=None, retry=None):
    return {"question_id": qid, "latency_ms": latency_ms, "exec_ok": exec_ok, "refused": refused,
            "rows": 3 if exec_ok else None, "prompt_tokens": 1000, "completion_tokens": 120, "qm_llm_calls": 4,
            "qm_node_latency_ms": nodes, "qm_schema_retry": retry,
            "qm_node_tokens": {"response_generator": {"llm_calls": 1, "prompt_tokens": 300,
                                                      "completion_tokens": 40}} if nodes else None}


AFTER_NODES = {"schema_retriever": 300.0, "sql_generator": 2500.0, "semantic_verifier": 2000.0,
               "optimizer": 1500.0, "executor": 5.0, "result_verifier": 900.0, "response_generator": 1800.0}


def test_latency_compare_uses_shared_questions_and_target() -> None:
    before = [_record("E1", 12000), _record("H1", 39000), _record("U1", 900, exec_ok=False, refused=True)]
    after = [_record("E1", 9000, nodes=AFTER_NODES), _record("H1", 11000, nodes=AFTER_NODES),
             _record("M3-E1", 8000, nodes=AFTER_NODES)]
    result = compare(before, after)
    assert result["shared_question_ids"] == ["E1", "H1"]
    assert result["after_same_questions"]["records"] == 2 and result["after_all"]["records"] == 3
    assert result["before"]["p95_s"] == 39.0 and result["before"]["per_node"] == {}
    assert result["target_met"] is True
    node = result["after_all"]["per_node"]["response_generator"]
    assert node["mean_s"] == pytest.approx(1.8) and node["mean_completion_tokens"] == 40
    assert list(result["after_all"]["per_node"])[0] == "schema_retriever"  # pipeline order


def test_newcombe_and_mcnemar() -> None:
    diff, low, high = newcombe(20, 40, 30, 40, wilson)
    assert diff == pytest.approx(-25.0) and low < diff < high < 0
    assert newcombe(0, 0, 1, 2, wilson) is None
    assert mcnemar_exact(0, 0) == 1.0 and mcnemar_exact(0, 6) == pytest.approx(0.03125)


def _rows(correct_ids, refused_ids=()):
    kinds = {"E1": ("easy", "reference"), "E2": ("easy", "reference"), "H1": ("hard", "reference"),
             "U1": ("unanswerable", "unanswerable"), "A1": ("ambiguous", "ambiguous")}
    return [{"id": qid, "group": "main", "set": s, "kind": k, "correct": qid in correct_ids,
             "record": {"refused": qid in refused_ids, "exec_ok": qid not in refused_ids,
                        "latency_ms": 9000, "qm_llm_calls": 4, "prompt_tokens": 900, "completion_tokens": 100,
                        "qm_schema_retry": {"triggered": qid == "E2", "trigger": None,
                                            "outcome": "answered" if qid == "E2" else None}}}
            for qid, (s, k) in kinds.items()]


def test_ablation_table_deltas_and_markdown() -> None:
    scored = {"r1": {
        "all_enabled": _rows({"E1", "E2", "H1", "U1", "A1"}, refused_ids={"U1"}),
        "without_semantic": _rows({"E1", "E2", "A1"}),           # answers U1 -> fabrication
        "without_schema_retry": _rows({"E1", "H1", "U1", "A1"}, refused_ids={"U1", "E2"}),
    }}
    table = ablation_table(scored, wilson)
    semantic = table["without_semantic"]
    assert semantic["metrics"]["fabrications"]["k"] == 1
    assert semantic["metrics"]["correct_all"]["delta_pp"][0] == pytest.approx(-40.0)
    assert semantic["paired_vs_full"] == {"n": 5, "lost": 2, "gained": 0, "p_exact_mcnemar": 0.5}
    assert table["without_schema_retry"]["metrics"]["over_refusal"]["k"] == 1
    assert "delta_pp" not in table["all_enabled"]["metrics"]["correct_all"]
    assert table["all_enabled"]["cost"]["schema_retry_answered"] == 1
    text = markdown("stakeholder60", table)
    assert "- Semantic verifier" in text and "Δ vs full" in text
    with pytest.raises(ValueError, match="all_enabled"):
        ablation_table({"r1": {"without_semantic": scored["r1"]["without_semantic"]}}, wilson)


def test_every_ablation_variant_maps_to_cli_options() -> None:
    variants = experiment_variants(include_syntax=True)
    assert variant_cli(variants["all_enabled"]) == ["--schema-mode", "neo4j"]
    assert variant_cli(variants["without_neo4j"]) == ["--schema-mode", "flat"]
    assert variant_cli(variants["without_schema_retry"])[-2:] == ["--disable", "schema_retry"]
    assert all(len(variant_cli(flags)) == 4 for name, flags in variants.items()
               if name not in {"all_enabled", "without_neo4j"})


def test_live_ablation_dry_run_needs_no_gateway(capsys) -> None:
    assert run_live_ablation(["--dataset", "stakeholder", "--dry-run", "--variants", "all_enabled,without_semantic"]) == 0
    out = capsys.readouterr().out
    assert "without_semantic" in out and "--disable semantic" in out


def test_figures_render_from_synthetic_summaries(tmp_path) -> None:
    before = [_record("E1", 12000), _record("H1", 39000)]
    after = [_record("E1", 9000, nodes=AFTER_NODES), _record("H1", 11000, nodes=AFTER_NODES)]
    latency = tmp_path / "latency.json"
    latency.write_text(json.dumps(compare(before, after)), encoding="utf-8")
    scored = {"r1": {name: _rows({"E1", "E2", "H1", "U1", "A1"} - drop, refused_ids={"U1"})
                     for name, drop in (("all_enabled", set()), ("without_neo4j", {"H1"}),
                                        ("without_semantic", {"U1"}), ("without_result_verifier", set()),
                                        ("without_optimizer", set()), ("without_schema_retry", {"E2"}))}}
    ablation = tmp_path / "ablation.json"
    ablation.write_text(json.dumps({"datasets": {"stakeholder60": {"variants": ablation_table(scored, wilson)}}}),
                        encoding="utf-8")
    out = tmp_path / "poster"
    assert make_figures(["--out", str(out), "--latency", str(latency), "--ablation", str(ablation)]) == 0
    for name in ("m3_architecture", "m3_latency", "m3_ablation"):
        assert (out / f"{name}.pdf").stat().st_size > 0 and (out / f"{name}.png").exists()


def test_missing_inputs_skip_panels_but_draw_architecture(tmp_path, capsys) -> None:
    assert make_figures(["--out", str(tmp_path), "--latency", str(tmp_path / "x.json"),
                         "--ablation", str(tmp_path / "y.json")]) == 0
    assert (tmp_path / "m3_architecture.pdf").exists() and not (tmp_path / "m3_latency.pdf").exists()
    assert "skipped latency panel" in capsys.readouterr().out
