"""Provider boundary; the starter deliberately uses deterministic offline SQL."""

from __future__ import annotations

import json
import os
import re
from typing import Protocol
import urllib.error
import urllib.request


class SQLProvider(Protocol):
    """Replaceable SQL generation contract, independent of an SDK or model."""

    def generate(self, question: str, schema_context: str) -> str:
        """Return SQL for a question, or raise ValueError if unsupported."""
        ...


class MockProvider:
    """Answer only documented demo templates without an API key or network."""

    def generate(self, question: str, schema_context: str) -> str:
        """Generate deterministic demo SQL; unsupported input is refused."""
        normalized = " ".join(question.lower().strip().rstrip("?!.").split())
        top_customers = re.fullmatch(
            r"who are the top ([1-9][0-9]?) customers by total spending", normalized
        )
        if top_customers:
            return (
                "SELECT c.name, SUM(o.amount) AS total_spending "
                "FROM customers AS c JOIN orders AS o ON c.customer_id = o.customer_id "
                "GROUP BY c.customer_id, c.name "
                "ORDER BY total_spending DESC, c.customer_id "
                f"LIMIT {int(top_customers.group(1))}"
            )
        if normalized in {"how many customers are there", "how many customers"}:
            return "SELECT COUNT(*) AS customer_count FROM customers"
        raise ValueError(
            "The offline mock supports only 'Who are the top 3 customers by total spending?' "
            "and 'How many customers are there?'. A real SQL provider is a future implementation."
        )


class OpenAICompatibleProvider:
    """OpenAI-compatible chat completion provider using the standard library."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def _resolve_api_key(self) -> str:
        key = (
            self.api_key
            or os.environ.get("OPENCODE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        if not key:
            raise ValueError(
                "API key not found. Set OPENCODE_API_KEY or OPENAI_API_KEY in the environment or .env."
            )
        return key.strip()

    def _resolve_base_url(self) -> str:
        url = (
            self.base_url
            or os.environ.get("OPENCODE_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://openai.rc.asu.edu/v1"
        )
        return url.strip().rstrip("/")

    def _resolve_model(self) -> str:
        model = (
            self.model
            or os.environ.get("COMPLETION_MODEL")
            or os.environ.get("OPENCODE_MODEL")
            or os.environ.get("OPENAI_MODEL")
        )
        if not model:
            raise ValueError(
                "Model name not found. Set COMPLETION_MODEL, OPENCODE_MODEL, or OPENAI_MODEL in the environment or .env."
            )
        return model.strip()

    def generate(self, question: str, schema_context: str) -> str:
        """Call OpenAI-compatible chat completion and return the generated SQL."""
        api_key = self._resolve_api_key()
        base_url = self._resolve_base_url()
        model = self._resolve_model()

        endpoint = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{schema_context}\n\nUser Question:\n{question}",
                }
            ],
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "QueryMind/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                res_json = json.loads(body)
                choices = res_json.get("choices")
                if not choices or not isinstance(choices, list):
                    raise ValueError(f"Provider returned invalid response format: {body[:200]}")
                message = choices[0].get("message", {})
                content = message.get("content", "")
                return (content or "").strip()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            raise ValueError(f"Provider HTTP error {exc.code}: {err_body or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Provider network error: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            raise ValueError(f"Provider connection error: {exc}") from exc


def get_provider(name: str = "mock") -> SQLProvider:
    """Return the explicitly selected provider; never silently enable network."""
    normalized = name.lower().strip()
    if normalized == "mock":
        return MockProvider()
    if normalized in {"opencode", "openai", "openai-compatible", "live"}:
        return OpenAICompatibleProvider()
    raise ValueError(
        f"Provider {name!r} is not implemented; use 'mock', 'opencode', or 'openai'."
    )
