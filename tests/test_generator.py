"""Focused tests for SQL generation, structured repair prompting, and providers."""

from __future__ import annotations

import io
import json
import urllib.error
import pytest

from src.agents.generator import (
    build_prompt_context,
    generate_sql,
    normalize_sql,
)
from src.llm import (
    MockProvider,
    OpenAICompatibleProvider,
    get_provider,
)


class CapturingProvider:
    """Capture question and schema_context passed to the provider."""

    def __init__(self, response: str = "SELECT 1 AS value") -> None:
        self.response = response
        self.last_question: str = ""
        self.last_context: str = ""

    def generate(self, question: str, schema_context: str) -> str:
        self.last_question = question
        self.last_context = schema_context
        return self.response


# ---------------------------------------------------------------------------
# 1. MockProvider Regressions
# ---------------------------------------------------------------------------

def test_mock_provider_customer_count() -> None:
    provider = MockProvider()
    sql = provider.generate("How many customers are there?", "TABLE customers (customer_id INT)")
    assert sql == "SELECT COUNT(*) AS customer_count FROM customers"


def test_mock_provider_top_spending() -> None:
    provider = MockProvider()
    sql = provider.generate("Who are the top 3 customers by total spending?", "TABLE customers ...")
    assert "LIMIT 3" in sql
    assert "SUM(o.amount) AS total_spending" in sql


def test_mock_provider_unsupported_question_raises() -> None:
    provider = MockProvider()
    with pytest.raises(ValueError, match="offline mock supports only"):
        provider.generate("What is the average order value?", "TABLE orders (amount REAL)")


def test_generate_sql_default_uses_mock_offline() -> None:
    sql = generate_sql("How many customers are there?", "TABLE customers (id INT)")
    assert sql == "SELECT COUNT(*) AS customer_count FROM customers"


# ---------------------------------------------------------------------------
# 2. Text-to-SQL Prompt Formatting
# ---------------------------------------------------------------------------

def test_generation_prompt_contains_required_rules() -> None:
    capturing = CapturingProvider()
    generate_sql(
        question="How many products are in stock?",
        schema_context="TABLE products (id INT, stock INT)",
        provider=capturing,
    )

    assert capturing.last_question == "How many products are in stock?"
    context = capturing.last_context

    # Core rules must be present
    assert "SQLite" in context
    assert "SELECT" in context and "WITH" in context
    assert "INSERT" in context and "DELETE" in context  # read-only forbidden list
    assert "explicitly present in the supplied database schema" in context or "only tables" in context.lower()
    assert "JOIN" in context
    assert "NOT_ANSWERABLE" in context
    assert "TABLE products (id INT, stock INT)" in context


# ---------------------------------------------------------------------------
# 3. Structured Repair Prompting
# ---------------------------------------------------------------------------

def test_repair_prompt_contains_previous_sql_and_error() -> None:
    capturing = CapturingProvider()
    feedback = (
        "Previous SQL:\n"
        "SELECT absent_col FROM products\n\n"
        "Verification failure:\n"
        "no such column: absent_col"
    )

    generate_sql(
        question="What are the product names?",
        schema_context="TABLE products (id INT, name TEXT)",
        provider=capturing,
        feedback=feedback,
    )

    context = capturing.last_context
    assert "REPAIR TASK" in context
    assert "Previous SQL:" in context
    assert "SELECT absent_col FROM products" in context
    assert "Verification failure:" in context
    assert "no such column: absent_col" in context
    assert "TABLE products (id INT, name TEXT)" in context


def test_repair_prompt_handles_plain_error_string() -> None:
    capturing = CapturingProvider()
    generate_sql(
        question="What are the product names?",
        schema_context="TABLE products (id INT, name TEXT)",
        provider=capturing,
        feedback="no such column: absent_col",
    )

    context = capturing.last_context
    assert "REPAIR TASK" in context
    assert "no such column: absent_col" in context


# ---------------------------------------------------------------------------
# 4. Output Normalization
# ---------------------------------------------------------------------------

def test_normalize_plain_sql() -> None:
    assert normalize_sql("SELECT 1 AS val") == "SELECT 1 AS val"
    assert normalize_sql("   SELECT 1 AS val \n\n ") == "SELECT 1 AS val"


def test_normalize_markdown_fences() -> None:
    fenced_sql = "```sql\nSELECT name FROM customers;\n```"
    assert normalize_sql(fenced_sql) == "SELECT name FROM customers;"

    fenced_sqlite = "```sqlite\nSELECT name FROM customers;\n```"
    assert normalize_sql(fenced_sqlite) == "SELECT name FROM customers;"

    fenced_plain = "```\nSELECT name FROM customers;\n```"
    assert normalize_sql(fenced_plain) == "SELECT name FROM customers;"


def test_normalize_not_answerable() -> None:
    assert normalize_sql("NOT_ANSWERABLE:cost") == "NOT_ANSWERABLE:cost"
    fenced_refusal = "```sql\nNOT_ANSWERABLE:profit_margin\n```"
    assert normalize_sql(fenced_refusal) == "NOT_ANSWERABLE:profit_margin"


def test_normalize_edge_cases() -> None:
    assert normalize_sql("") == ""
    assert normalize_sql("   ") == ""
    assert normalize_sql(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Live Provider Configuration and Resolution
# ---------------------------------------------------------------------------

def test_get_provider_registration() -> None:
    assert isinstance(get_provider("mock"), MockProvider)
    assert isinstance(get_provider("opencode"), OpenAICompatibleProvider)
    assert isinstance(get_provider("openai"), OpenAICompatibleProvider)
    assert isinstance(get_provider("openai-compatible"), OpenAICompatibleProvider)

    with pytest.raises(ValueError, match="is not implemented"):
        get_provider("unsupported-vendor")


def test_live_provider_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("OPENCODE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("COMPLETION_MODEL", "test-model")

    provider = OpenAICompatibleProvider()
    with pytest.raises(ValueError, match="API key not found"):
        provider.generate("How many rows?", "TABLE t (id INT)")


def test_live_provider_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    for var in ("COMPLETION_MODEL", "OPENCODE_MODEL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)

    provider = OpenAICompatibleProvider()
    with pytest.raises(ValueError, match="Model name not found"):
        provider.generate("How many rows?", "TABLE t (id INT)")


def test_live_provider_uses_custom_init_parameters() -> None:
    provider = OpenAICompatibleProvider(
        api_key="custom-key",
        base_url="https://custom.endpoint.com/v1",
        model="custom-model",
        temperature=0.5,
    )
    assert provider.api_key == "custom-key"
    assert provider.base_url == "https://custom.endpoint.com/v1"
    assert provider.model == "custom-model"
    assert provider.temperature == 0.5


# ---------------------------------------------------------------------------
# 6. Mocked Network Request & Response Handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base_url, model, expected_model", [
    ("https://openai.rc.asu.edu/v1", "openai/devstral2-123b", "devstral2-123b"),
    ("https://openai.rc.asu.edu/v1", "devstral2-123b", "devstral2-123b"),
    ("https://gateway.example/v1", "openai/devstral2-123b", "openai/devstral2-123b"),
])
def test_live_provider_successful_request(monkeypatch: pytest.MonkeyPatch, base_url, model, expected_model) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-secret-key")
    monkeypatch.setenv("COMPLETION_MODEL", model)
    monkeypatch.setenv("OPENCODE_BASE_URL", base_url)

    captured_request = {}

    class MockHTTPResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> MockHTTPResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def mock_urlopen(req: urllib.request.Request, timeout: float = 30.0) -> MockHTTPResponse:
        captured_request["url"] = req.full_url
        captured_request["headers"] = dict(req.headers)
        captured_request["data"] = json.loads(req.data.decode("utf-8"))
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": "```sql\nSELECT COUNT(*) FROM items;\n```"
                    }
                }
            ]
        }
        return MockHTTPResponse(json.dumps(response_payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OpenAICompatibleProvider()
    result = generate_sql("How many items?", "TABLE items (id INT)", provider=provider)

    # Output normalization removes the code fence
    assert result == "SELECT COUNT(*) FROM items;"

    # Verify request details
    assert captured_request["url"] == base_url + "/chat/completions"
    assert captured_request["headers"]["Authorization"] == "Bearer test-secret-key"
    assert captured_request["headers"]["Content-type"] == "application/json"
    assert captured_request["data"]["model"] == expected_model
    assert "items" in captured_request["data"]["messages"][0]["content"]


def test_live_provider_http_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setenv("COMPLETION_MODEL", "test-model")

    def mock_urlopen_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            url="https://openai.rc.asu.edu/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error": "Invalid API key"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_error)

    provider = OpenAICompatibleProvider()
    with pytest.raises(ValueError, match="Provider HTTP error 401"):
        provider.generate("How many items?", "TABLE items (id INT)")


def test_live_provider_url_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setenv("COMPLETION_MODEL", "test-model")

    def mock_urlopen_network_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_network_error)

    provider = OpenAICompatibleProvider()
    with pytest.raises(ValueError, match="Provider network error"):
        provider.generate("How many items?", "TABLE items (id INT)")

