"""The UI imports safely and delegates queries to the public orchestrator."""

from contextlib import nullcontext
from types import SimpleNamespace


def test_ui_import_exposes_entry_point() -> None:
    import app

    assert callable(app.main)


def test_ui_does_not_run_an_empty_question(monkeypatch) -> None:
    import app

    messages: list[str] = []
    fake = SimpleNamespace(
        set_page_config=lambda **kwargs: None,
        title=lambda value: None,
        caption=lambda value: None,
        text_input=lambda *args, **kwargs: "  ",
        button=lambda *args, **kwargs: True,
        warning=messages.append,
    )
    monkeypatch.setattr(app, "st", fake)
    def unexpected_run(*args, **kwargs) -> None:
        raise AssertionError("Should not run")

    monkeypatch.setattr(app, "run_querymind", unexpected_run)
    app.main()
    assert messages == ["Enter a business question."]


def test_ui_calls_public_orchestrator_and_shows_refusal(monkeypatch) -> None:
    import app

    messages: list[str] = []
    calls: list[tuple[str, str]] = []

    def run(question: str, *, schema_mode: str) -> dict:
        calls.append((question, schema_mode))
        return {"status": "refused", "final_answer": "Unsupported starter question.", "trace": []}

    fake = SimpleNamespace(
        set_page_config=lambda **kwargs: None,
        title=lambda value: None,
        caption=lambda value: None,
        text_input=lambda *args, **kwargs: "Find unavailable fields",
        button=lambda *args, **kwargs: True,
        spinner=lambda value: nullcontext(),
        subheader=lambda value: None,
        write=messages.append,
        info=lambda value: None,
        expander=lambda value: nullcontext(),
        json=lambda value: None,
    )
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app, "run_querymind", run)
    app.main()
    assert calls == [("Find unavailable fields", "flat")]
    assert "Unsupported starter question." in messages


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
        "safety_verifier",
        "safety_ok",
    ) == "failed"
