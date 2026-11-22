"""Member 3's contribution to the 60-question set: format, mix, and reference SQL."""

from collections import Counter
from pathlib import Path
import sqlite3

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval/new_questions/member3.yaml"
STAKEHOLDER_DB = ROOT / "data/stakeholder_analytics.db"
FIELDS = {"id", "question", "set", "kind", "ordered", "reference_sql", "missing_field",
          "accept_missing", "undefined_terms", "note"}


def _items():
    return yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))


def test_member3_mix_and_format():
    items = _items()
    assert Counter(item["set"] for item in items) == {"easy": 2, "hard": 3, "unanswerable": 2, "ambiguous": 1}
    ids = [item["id"] for item in items]
    # The M3- prefix keeps IDs disjoint from the existing E/H/U/A ids and other members' files.
    assert len(ids) == len(set(ids)) and all(i.startswith("M3-") for i in ids)
    for item in items:
        assert set(item) <= FIELDS, item["id"]  # the stakeholder loader rejects unknown keys
        if item["kind"] == "reference":
            assert item["reference_sql"].strip().upper().startswith(("SELECT", "WITH"))
        if item["kind"] == "unanswerable":
            assert item["accept_missing"]
        if item["kind"] == "ambiguous":
            assert item["undefined_terms"]


@pytest.mark.skipif(not STAKEHOLDER_DB.exists(), reason="run `make stakeholder-baseline` to seed the stakeholder DB")
def test_member3_reference_sql_runs_and_is_non_empty():
    connection = sqlite3.connect(f"file:{STAKEHOLDER_DB}?mode=ro", uri=True)
    try:
        for item in _items():
            if item["kind"] != "reference":
                continue
            rows = connection.execute(item["reference_sql"]).fetchall()
            assert rows, f"{item['id']} reference returns no rows"
    finally:
        connection.close()
