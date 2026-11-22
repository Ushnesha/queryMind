"""The merged evaluation set eval/questions_60.yaml: ids, format, counts, and reference SQL.

The set is partial while member files are pending. The current counts are pinned
so any change is deliberate; the plan's final mix is an xfail test until the
pending members land.
"""

from collections import Counter
from pathlib import Path
import sqlite3

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval/questions_60.yaml"
STAKEHOLDER_DB = ROOT / "data/stakeholder_analytics.db"
FIELDS = {"id", "question", "set", "kind", "ordered", "reference_sql", "missing_field",
          "accept_missing", "undefined_terms", "note"}

# member5.yaml is replaced by member5_converted.yaml; M4-E1 and M5_H3 are dropped as duplicates.
PENDING_MEMBERS: list[str] = []

PLAN_SET_TARGET = {"easy": 15, "hard": 20, "unanswerable": 15, "ambiguous": 10}


def _items():
    return yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))


def test_loads_as_a_list_of_questions():
    items = _items()
    assert isinstance(items, list) and all(isinstance(item, dict) for item in items)


def test_ids_are_unique():
    ids = [item["id"] for item in _items()]
    assert len(ids) == len(set(ids))


def test_only_allowed_fields_and_required_fields_per_kind():
    for item in _items():
        assert set(item) <= FIELDS, item["id"]  # the stakeholder loader rejects unknown keys
        if item["kind"] == "reference":
            assert item["reference_sql"].strip().upper().startswith(("SELECT", "WITH")), item["id"]
        if item["kind"] == "unanswerable":
            assert item["accept_missing"], item["id"]
        if item["kind"] == "ambiguous":
            assert item["undefined_terms"], item["id"]


def test_no_duplicate_questions():
    texts = [item["question"].strip().lower() for item in _items()]
    assert len(texts) == len(set(texts))


def test_current_counts():
    items = _items()
    assert len(items) == 60
    assert Counter(item["set"] for item in items) == {
        "easy": 15,
        "hard": 20,
        "unanswerable": 15,
        "ambiguous": 10,
    }
    assert Counter(item["kind"] for item in items) == {"reference": 32, "unanswerable": 16, "ambiguous": 12}


def test_plan_final_mix():
    assert not PENDING_MEMBERS
    assert Counter(item["set"] for item in _items()) == PLAN_SET_TARGET


@pytest.mark.skipif(not STAKEHOLDER_DB.exists(), reason="run `make stakeholder-baseline` to seed the stakeholder DB")
def test_reference_sql_runs_and_is_non_empty():
    connection = sqlite3.connect(f"file:{STAKEHOLDER_DB}?mode=ro", uri=True)
    try:
        for item in _items():
            if item["kind"] != "reference":
                continue
            rows = connection.execute(item["reference_sql"]).fetchall()
            assert rows, f"{item['id']} reference returns no rows"
    finally:
        connection.close()
