"""Compatible request contract verified with fake HTTP, without credentials/network."""

from io import BytesIO
import json
from urllib.error import HTTPError

import pytest

from src.schema.experiment_provider import OpenCodeProvider


def test_provider_uses_completion_model_env_without_reading_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENCODE_API_KEY", "test-only")
    monkeypatch.setenv("COMPLETION_MODEL", "openai/devstral2-123b")
    provider = OpenCodeProvider.from_env()
    assert provider.model == "openai/devstral2-123b" and provider.temperature == 0
    assert provider.api_model == "devstral2-123b"
    assert "test-only" not in repr(provider)


def test_provider_request_only_differs_by_schema_context(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data), timeout))
        return BytesIO(json.dumps({"choices": [{"message": {"content": "```sql\nSELECT 1\n```"}}]}).encode())

    monkeypatch.setattr("src.schema.experiment_provider.urlopen", fake_urlopen)
    provider = OpenCodeProvider("https://example.test/v1", "test-only", "openai/devstral2-123b")
    assert provider.generate("same question", "flat schema") == "SELECT 1"
    assert provider.generate("same question", "graph schema") == "SELECT 1"
    before, after = calls[0][1], calls[1][1]
    assert calls[0][0] == calls[1][0] == "https://example.test/v1/chat/completions"
    assert before["model"] == after["model"] == "devstral2-123b"
    assert before["messages"][0] == after["messages"][0]
    assert before["temperature"] == after["temperature"] == 0
    assert before["messages"][1]["content"].endswith("Question:\nsame question")
    assert after["messages"][1]["content"].endswith("Question:\nsame question")


def test_provider_http_errors_do_not_include_keys_or_response_body(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise HTTPError("https://example.test", 401, "test-only", {}, None)

    monkeypatch.setattr("src.schema.experiment_provider.urlopen", fail)
    provider = OpenCodeProvider("https://example.test/v1", "test-only", "model")
    with pytest.raises(RuntimeError, match=r"HTTP 401") as captured:
        provider.generate("question", "schema")
    assert "test-only" not in str(captured.value)


def test_provider_requires_plain_url_and_explicit_credentials() -> None:
    with pytest.raises(ValueError, match="plain"):
        OpenCodeProvider("[https://example.test/v1](https://example.test/v1)", "test-only", "model")
    with pytest.raises(ValueError, match="COMPLETION_MODEL"):
        OpenCodeProvider("https://example.test/v1", "", "model")
