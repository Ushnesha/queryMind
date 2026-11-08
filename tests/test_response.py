"""Natural-language responses stay grounded in executed results."""

import pytest

from src.agents.response import generate_response


def singer_state():
    return {"question": "How many singers are there?", "status": "success",
            "answerable": True, "sql": "SELECT COUNT(*) FROM singer",
            "columns": ["COUNT(*)"], "rows": [[6]], "metrics": {}}


def test_model_receives_actual_result_and_original_question():
    class Provider:
        def generate(self, question, context):
            assert question == "How many singers are there?"
            assert '"rows": [[6]]' in context
            assert "ONLY the executed query results" in context
            return "There are 6 singers."

    state = singer_state()
    assert generate_response(state, provider=Provider()) == "There are 6 singers."
    assert state["metrics"]["response_generation"]["mode"] == "model"


@pytest.mark.parametrize("reply", ["", "SELECT COUNT(*) FROM singer", None])
def test_answer_failure_preserves_successful_count(reply):
    class Provider:
        def generate(self, question, context):
            if reply is None:
                raise TimeoutError("Service timeout")
            return reply

    state = singer_state()
    assert generate_response(state, provider=Provider()) == "There are 6 singers."
    assert state["status"] == "success"
    assert state["metrics"]["response_generation"]["mode"] == "fallback"


def test_refusals_and_empty_results_do_not_call_answer_model():
    class Provider:
        def generate(self, *args):
            raise AssertionError("Must not call model")

    state = singer_state()
    state.update(status="refused", answerable=False, missing_fields=["cost"])
    assert "cost" in generate_response(state, provider=Provider())
    state = singer_state()
    state["rows"] = []
    assert "no matching rows" in generate_response(state, provider=Provider())
