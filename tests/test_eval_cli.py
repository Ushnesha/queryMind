"""CLI artifact, paired population, and offline replay regression tests."""

import json
from pathlib import Path

import pytest

from scripts.run_ablation import main as ablation_main
from scripts.run_eval import main, render_report, select_questions, write_artifacts
from src.config import PROJECT_ROOT
from src.evaluation import load_questions, score_records


def test_committed_synthetic_traces_are_scored_offline(db_path: Path) -> None:
    records = [json.loads(line) for line in (PROJECT_ROOT / 'eval/fixtures/member5_traces.jsonl').read_text().splitlines()]
    ids = {record['question_id'] for record in records}
    questions = [q for q in load_questions(PROJECT_ROOT / 'eval/milestone2.yaml') if q['id'] in ids]
    report = score_records(questions, records, db_path=db_path)
    metrics = report['metrics']
    assert metrics['correct_cases'] == 3
    assert metrics['scored_cases'] == 5
    assert metrics['unanswerable_refusal_rate'] == .5
    assert metrics['raw_unanswerable_refusal_rate'] == 1
    assert metrics['ambiguity_flagged_rate'] == 1
    assert metrics['p50_latency_ms'] == 30
    assert metrics['p95_latency_ms'] == 48


def test_default_subsets_have_fixed_representative_ids() -> None:
    questions = load_questions(PROJECT_ROOT / 'eval/milestone2.yaml')
    assert len(questions) == 17
    assert len(select_questions(questions, 'b2')) == 7
    assert len(select_questions(questions, 'ablation')) == 10
    assert len(select_questions(questions, 'schema')) == 8
    assert any(q['answerable'] is False for q in select_questions(questions, 'b2'))
    assert any(q['ambiguous'] is True for q in select_questions(questions, 'b2'))


def test_all_arm_artifacts_replay_paired_population(db_path: Path, tmp_path: Path, capsys) -> None:
    output = tmp_path / 'comparison.json'
    markdown = tmp_path / 'comparison.md'
    assert main(['--arm', 'all', '--db-path', str(db_path), '--output', str(output), '--markdown', str(markdown)]) == 0
    report = json.loads(output.read_text())
    assert {len(r['cases']) for r in report['comparison'].values()} == {7}
    assert {len(r['cases']) for r in report['full_evaluation'].values()} == {17}
    assert report['comparison']['b2-small']['metrics']['generation_calls_per_question'] == 3
    assert len(output.with_suffix('.jsonl').read_text().splitlines()) == 55
    assert 'preliminary' in markdown.read_text()
    replay = tmp_path / 'replay.json'
    assert main(['--arm', 'querymind', '--traces', str(output.with_suffix('.jsonl')), '--trace-experiment', 'comparison', '--db-path', str(db_path), '--output', str(replay)]) == 0
    replayed = json.loads(replay.read_text())
    assert replayed['metrics'] == report['comparison']['querymind']['metrics']
    with pytest.raises(SystemExit) as exc:
        main(['--arm', 'querymind', '--traces', str(output.with_suffix('.jsonl')), '--db-path', str(db_path), '--output', str(replay)])
    assert exc.value.code == 2
    assert '--trace-experiment' in capsys.readouterr().err


def test_b2_preliminary_cli_rejects_full_fixture(db_path: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['--arm', 'b2', '--subset', 'all', '--db-path', str(db_path), '--output', str(tmp_path / 'b2.json')])
    assert exc.value.code == 2


def test_ablation_cli_writes_each_configuration_case(db_path: Path, tmp_path: Path) -> None:
    output = tmp_path / 'ablation.json'
    assert ablation_main(['--db-path', str(db_path), '--output', str(output)]) == 0
    report = json.loads(output.read_text())
    assert len(report['variants']) == 5
    assert len(output.with_suffix('.jsonl').read_text().splitlines()) == 50
    assert report['variants']['without_neo4j']['flags']['schema_mode'] == 'flat'


def test_artifact_destinations_cannot_overwrite_each_other(tmp_path: Path) -> None:
    destination = tmp_path / 'same.jsonl'
    with pytest.raises(ValueError, match='different files'):
        write_artifacts({'cases': [], 'metrics': {}}, destination)
    assert not destination.exists()


def test_reference_errors_are_visible_in_presentation() -> None:
    text = render_report({'scope': 'fixture', 'metrics': {'case_count': 2, 'scored_cases': 1, 'unscored_cases': 1, 'reference_error_count': 1, 'result_accuracy': 1}})
    assert '| Scored cases | 1.' in text
    assert '| Reference errors | 1.' in text


def test_replay_preserves_missing_expected_cases(db_path: Path, tmp_path: Path) -> None:
    traces = tmp_path / 'partial.jsonl'
    traces.write_text(json.dumps({'question_id': 'E1', 'state': {'status': 'success', 'rows': [[4]], 'columns': ['customer_count']}}) + '\n')
    output = tmp_path / 'partial.json'
    assert main(['--traces', str(traces), '--subset', 'b2', '--db-path', str(db_path), '--output', str(output)]) == 0
    report = json.loads(output.read_text())
    assert report['metrics']['case_count'] == 7
    assert report['metrics']['scored_cases'] == 1
    assert report['metrics']['unscored_cases'] == 6


def test_malformed_trace_line_has_clear_cli_error(tmp_path: Path, capsys) -> None:
    traces = tmp_path / 'invalid.jsonl'
    traces.write_text('[]\n')
    with pytest.raises(SystemExit) as exc:
        main(['--traces', str(traces), '--output', str(tmp_path / 'out.json')])
    assert exc.value.code == 2
    assert 'must be an object' in capsys.readouterr().err


def test_legacy_smoke_saves_all_five_states(db_path: Path, tmp_path: Path) -> None:
    output = tmp_path / 'smoke.json'
    assert ablation_main(['--question', 'How many customers are there?', '--db-path', str(db_path), '--output', str(output)]) == 0
    assert len(output.with_suffix('.jsonl').read_text().splitlines()) == 5
