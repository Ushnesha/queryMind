"""Semantic verifier: missing data, question/SQL intent alignment and the LLM judge."""

import json

import pytest

from src.verifiers import verify_semantics
from src.verifiers.cues import parse_schema

SCHEMA = """TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT
)

TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  order_date TEXT NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
)"""

TOP3_SQL = (
    "SELECT c.name, SUM(o.amount) AS total_spending FROM customers AS c "
    "JOIN orders AS o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.name "
    "ORDER BY total_spending DESC, c.customer_id LIMIT 3"
)


class FakeJudge:
    """Stands in for the LLM provider; records prompts and returns a fixed reply."""

    def __init__(self, reply: object) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def generate(self, question: str, schema_context: str) -> str:
        self.calls.append((question, schema_context))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def check(question: str, sql: str, schema: str = SCHEMA, **kwargs):
    return verify_semantics(question, sql, schema, use_llm=kwargs.pop("use_llm", False), **kwargs)


def test_schema_parser_reads_retriever_output_and_notes() -> None:
    info = parse_schema("-- Neo4j retrieval failed; using flat.\n" + SCHEMA)
    assert info.tables == {
        "customers": ["customer_id", "name", "email"],
        "orders": ["order_id", "customer_id", "amount", "order_date"],
    }
    assert info.notes == ["Neo4j retrieval failed; using flat."]


def test_valid_sql_passes_with_real_status() -> None:
    result = check("Who are the top 3 customers by total spending?", TOP3_SQL)
    assert result["matches_question"] is True and result["answerable"] is True
    assert result["status"] == "deterministic"
    assert "top-3 ranking" in result["reason"]
    assert any("tied" in a for a in result["assumptions"])


def test_count_question_passes() -> None:
    result = check("How many customers are there?", "SELECT COUNT(*) AS customer_count FROM customers")
    assert result["matches_question"] is True and result["answerable"] is True


def test_profit_margin_is_unanswerable_without_cost() -> None:
    result = check(
        "What is the profit margin per category?",
        "SELECT SUM(amount) FROM orders",
    )
    assert result["answerable"] is False
    assert result["matches_question"] is False
    assert "cost" in result["missing_fields"]
    assert "cost" in result["reason"]


def test_present_data_is_not_reported_missing() -> None:
    schema = SCHEMA.replace("amount REAL NOT NULL,", "amount REAL NOT NULL,\n  cost REAL,\n  category TEXT,")
    result = check("What is the profit margin per category?", "SELECT category, SUM(amount - cost) / SUM(amount) FROM orders GROUP BY category", schema)
    assert result["answerable"] is True
    assert result["missing_fields"] == []


@pytest.mark.parametrize(
    ("question", "sql", "fragment"),
    [
        ("Who are the top 3 customers by total spending?", TOP3_SQL.replace("LIMIT 3", "LIMIT 5"), "LIMIT 5"),
        ("Who are the top 3 customers by total spending?", TOP3_SQL.replace(" LIMIT 3", ""), "no LIMIT"),
        ("How many customers are there?", "SELECT name FROM customers", "COUNT"),
        ("What is the average order amount?", "SELECT SUM(amount) FROM orders", "AVG"),
        ("What is the total order amount?", "SELECT amount FROM orders", "SUM"),
        ("Who are the top 3 customers by total spending?", TOP3_SQL.replace("SUM(o.amount)", "COUNT(o.order_id)"), "no SUM"),
        ("Which customer has the highest order amount?", "SELECT customer_id FROM orders ORDER BY amount ASC LIMIT 1", "ascending"),
        ("Which order has the lowest amount?", "SELECT order_id FROM orders ORDER BY amount DESC LIMIT 1", "descending"),
        ("Which order has the highest amount?", "SELECT order_id FROM orders", "MAX/MIN"),
    ],
)
def test_intent_mismatch_requests_repair(question: str, sql: str, fragment: str) -> None:
    result = check(question, sql)
    assert result["answerable"] is True
    assert result["matches_question"] is False
    assert fragment in result["reason"]


def test_total_of_things_may_be_a_count() -> None:
    result = check("What is the total number of orders?", "SELECT COUNT(*) FROM orders")
    assert result["matches_question"] is True
    result = check("How many total orders did each customer place?", "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id")
    assert result["matches_question"] is True


def test_at_least_filter_is_not_a_superlative() -> None:
    result = check("Which customers placed at least 2 orders?", "SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) >= 2")
    assert result["matches_question"] is True


def test_missing_inputs_cannot_be_answered() -> None:
    result = check("How many customers?", "SELECT 1", "")
    assert result["answerable"] is False


def test_schema_fallback_note_becomes_assumption() -> None:
    result = check("How many customers are there?", "SELECT COUNT(*) FROM customers",
                   "-- Neo4j retrieval failed; check connectivity.\n" + SCHEMA)
    assert any("Neo4j retrieval failed" in a for a in result["assumptions"])


def test_llm_judge_agreement_is_merged() -> None:
    judge = FakeJudge({
        "matches_question": True, "answerable": True, "missing_fields": [],
        "assumptions": ["Spending means the sum of order amounts."],
        "reason": "Sums order amounts per customer.",
    })
    result = verify_semantics("Who are the top 3 customers by total spending?", TOP3_SQL, SCHEMA, provider=judge)
    assert result["status"] == "deterministic+llm"
    assert result["matches_question"] is True
    assert "Spending means the sum of order amounts." in result["assumptions"]
    question, prompt = judge.calls[0]
    assert question.startswith("Who are the top 3") and TOP3_SQL in prompt and "TABLE orders" in prompt


def test_llm_judge_can_reject_sql_the_rules_accept() -> None:
    judge = FakeJudge('```json\n{"matches_question": false, "answerable": true, "reason": "Uses email instead of name."}\n```')
    result = verify_semantics("How many customers are there?", "SELECT COUNT(email) FROM customers", SCHEMA, provider=judge)
    assert result["matches_question"] is False and result["answerable"] is True
    assert result["reason"].startswith("LLM judge:")


def test_llm_judge_can_report_missing_fields() -> None:
    judge = FakeJudge({"matches_question": False, "answerable": False, "missing_fields": ["loyalty_tier"], "reason": "No loyalty tier column."})
    result = verify_semantics("Which customers are gold tier?", "SELECT name FROM customers", SCHEMA, provider=judge)
    assert result["answerable"] is False and result["missing_fields"] == ["loyalty_tier"]


@pytest.mark.parametrize("reply", [ValueError("network down"), "not json", {"reason": "no booleans"}])
def test_llm_judge_failure_falls_back_to_rules(reply: object) -> None:
    result = verify_semantics("How many customers are there?", "SELECT COUNT(*) FROM customers", SCHEMA, provider=FakeJudge(reply))
    assert result["status"] == "deterministic"
    assert result["matches_question"] is True
    assert any("LLM semantic judge unavailable" in a for a in result["assumptions"])


def test_rules_refusal_skips_the_llm_call() -> None:
    judge = FakeJudge({"matches_question": True, "answerable": True, "reason": "fine"})
    result = verify_semantics("What is the profit margin per category?", "SELECT 1", SCHEMA, provider=judge)
    assert result["answerable"] is False and judge.calls == []


def test_default_mock_configuration_does_not_call_a_model() -> None:
    result = verify_semantics("How many customers are there?", "SELECT COUNT(*) FROM customers", SCHEMA)
    assert result["status"] == "deterministic"
