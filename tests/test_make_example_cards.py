import sqlite3

import pytest

from scripts.make_example_cards import b0_contrast, card_from_record, crop, make_strip, read_record, same_question


def success(**kw):
    rec = {"question": "Q?", "refused": False, "sql": "SELECT 1", "qm_final_answer": "One.", "rows": 1,
           "assumptions": "Assumed X", "qm_reason": "ok"}
    return {**rec, **kw}


def test_crop_keeps_words_and_marks_the_cut():
    assert crop("short answer") == "short answer"
    cut = crop("one two three four five six", limit=14)
    assert cut == "one two three..." and "\n" not in cut


def test_success_card_shows_sql_answer_and_assumption():
    card = card_from_record(success())
    assert card["refused"] is False and card["sql"] == "SELECT 1"
    assert card["answer"] == "One." and card["note"] == "Assumed X" and card["tag"] == "Assumption stated"


def test_refused_card_has_no_sql_and_shows_the_refusal_reason():
    card = card_from_record(success(refused=True, sql="NOT_ANSWERABLE:x", qm_reason="Data is missing: cost"))
    assert card["sql"] is None and card["note"] is None
    assert card["answer"] == "Data is missing: cost" and card["refused"] is True


def test_same_question_ignores_case_and_end_punctuation():
    assert same_question("Show sales trends over time.", "Show sales trends over time")
    assert not same_question("Who are our top customers?", "Who are our most active customers?")


def test_b0_contrast_runs_the_recorded_sql_read_only(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (category TEXT, margin REAL)")
    conn.execute("INSERT INTO t VALUES ('Toys', 0.0), ('Books', 12.5)")
    conn.commit()
    conn.close()
    rec = {"sql": "SELECT category, margin FROM t ORDER BY category"}
    assert b0_contrast(rec, db) == "Books 12.5%; Toys 0.0%"
    assert b0_contrast(rec, tmp_path / "missing.db") is None


def test_read_record_finds_a_question_and_fails_loudly(tmp_path):
    folder = tmp_path / "stakeholder" / "r1"
    folder.mkdir(parents=True)
    (folder / "querymind__main.jsonl").write_text('{"question_id": "A1", "question": "Q?"}\n', encoding="utf-8")
    assert read_record(tmp_path, "r1", "querymind", "A1")["question"] == "Q?"
    with pytest.raises(KeyError):
        read_record(tmp_path, "r1", "querymind", "Z9")


def test_strip_writes_a_pdf(tmp_path):
    cards = [card_from_record(success()), card_from_record(success(refused=True, qm_reason="no"))]
    out = make_strip(cards, [None, "Toys 0.0%"], tmp_path / "strip.pdf")
    assert out.read_bytes().startswith(b"%PDF")
