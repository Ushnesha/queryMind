"""Presentation contracts exercised without credentials or a Streamlit server."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import orchestrator


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_ui_import_exposes_entry_point() -> None:
    import app

    assert callable(app.main)


def test_ui_does_not_run_an_empty_question(monkeypatch) -> None:
    def unexpected_run(*args, **kwargs):
        raise AssertionError("Should not run")

    monkeypatch.setattr(orchestrator, "run_querymind", unexpected_run)
    at = AppTest.from_file(str(APP)).run()
    at.text_input[0].set_value("  ")
    at.button[0].click().run()
    assert not at.exception
    assert at.warning[0].value == "Enter a business question."


def test_ui_calls_public_orchestrator_and_shows_missing_field_refusal(monkeypatch) -> None:
    calls = []

    def run(question, *, schema_mode):
        calls.append((question, schema_mode))
        return {
            "question": question, "status": "refused", "answerable": False,
            "missing_fields": ["product cost"],
            "semantic_reason": "Profit margin requires product cost, which is absent.",
            "final_answer": "No reliable answer.", "trace": [],
        }

    monkeypatch.setattr(orchestrator, "run_querymind", run)
    at = AppTest.from_file(str(APP)).run()
    at.text_input[0].set_value("What is the profit margin?")
    at.button[0].click().run()
    assert not at.exception
    assert calls == [("What is the profit margin?", "flat")]
    assert at.warning[0].value == "QueryMind cannot reliably answer this question."
    output = "\n".join(item.value for item in at.markdown)
    assert "Missing field: product cost" in output
    assert "Reason: Profit margin requires product cost, which is absent." in output
    assert "✓ Semantic verification" not in output


def test_ui_displays_result_sql_trace_and_retains_completed_answer(monkeypatch) -> None:
    calls = []

    def run(question, *, schema_mode):
        calls.append(question)
        return {
            "question": question, "status": "success", "answerable": True,
            "final_answer": "There are four customers.",
            "columns": ["customer_count"], "rows": [[4]],
            "sql": "SELECT COUNT(*) AS customer_count FROM customers",
            "original_sql": "SELECT COUNT(*) AS customer_count FROM customers",
            "safety_ok": True, "syntax_ok": True,
            "semantic_ok": False, "result_ok": False,
            "trace": [
                {"node": "schema_retriever", "status": "pass"},
                {"node": "safety_verifier", "status": "pass"},
                {"node": "syntax_verifier", "status": "pass"},
                {"node": "semantic_verifier", "status": "placeholder"},
                {"node": "optimizer", "status": "pass"},
                {"node": "executor", "status": "pass"},
                {"node": "result_verifier", "status": "placeholder"},
            ],
        }

    monkeypatch.setattr(orchestrator, "run_querymind", run)
    at = AppTest.from_file(str(APP)).run()
    at.text_input[0].set_value("How many customers are there?")
    at.button[0].click().run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0, 0] == 4
    assert at.code[0].value == "SELECT COUNT(*) AS customer_count FROM customers"
    assert [item.value for item in at.subheader] == [
        "Answer", "Result", "Generated SQL", "Assumptions", "Verification", "Agent Trace",
    ]
    output = "\n".join(item.value for item in at.markdown)
    assert "✓ SQL safe" in output and "✓ Syntax valid" in output
    assert "Semantic verification: starter checks only" in output
    assert "Result sanity: starter checks only" in output
    assert "Optimizer: SQL unchanged" in output
    assert "Schema → Safety → Syntax → Semantic verify → Optimize → Execute → Result verify" in output
    at.run()
    assert not at.exception
    assert calls == ["How many customers are there?"]
    assert "There are four customers." in [item.value for item in at.markdown]


def test_ui_handles_public_entry_point_exception(monkeypatch) -> None:
    def run(*args, **kwargs):
        raise FileNotFoundError("Database missing; run make seed.")

    monkeypatch.setattr(orchestrator, "run_querymind", run)
    at = AppTest.from_file(str(APP)).run()
    at.text_input[0].set_value("How many customers?")
    at.button[0].click().run()
    assert not at.exception
    assert at.error[0].value == "QueryMind could not run: Database missing; run make seed."


def test_ui_verification_labels_do_not_overstate_placeholders() -> None:
    import app

    state = {
        "semantic_ok": True,
        "syntax_ok": False,
        "trace": [
            {"node": "semantic_verifier", "status": "placeholder"},
            {"node": "syntax_verifier", "status": "skipped"},
        ],
    }
    assert app._verification_label(state, "semantic_verifier", "semantic_ok") == "starter checks only"
    assert app._verification_label(state, "syntax_verifier", "syntax_ok") == "disabled"
    assert app._verification_label({"result_ok": False, "trace": []}, "result_verifier", "result_ok") == "not run"
    assert app._verification_label(
        {"safety_ok": True, "trace": [{"node": "safety_verifier", "status": "fail"}]},
        "safety_verifier", "safety_ok",
    ) == "failed"


def test_optimizer_preservation_needs_explicit_evidence() -> None:
    import app

    state = {
        "original_sql": "SELECT 1", "sql": "SELECT 2", "optimization_applied": True,
        "trace": [{"node": "optimizer", "status": "pass"}],
    }
    assert app._optimizer_label(state) == "result preservation not recorded"
    state["metrics"] = {"optimizer_result_equal": True}
    assert app._optimizer_label(state) == "passed"
    state["metrics"]["optimizer_result_equal"] = False
    assert app._optimizer_label(state) == "result preservation failed"
