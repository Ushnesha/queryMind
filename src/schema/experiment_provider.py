"""Explicit ASU/OpenAI-compatible provider adapter for paired schema experiments.

This module does not alter the orchestrator owner's provider registry. Imports
and configuration inspection never send requests. Only ``generate`` does.
"""

from dataclasses import dataclass, field
import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_SYSTEM_PROMPT = (
    "Translate the user's question into SQLite SQL using only the supplied schema. "
    "Return exactly one read-only SELECT or WITH statement, without Markdown or explanations. "
    "Use the declared foreign keys for joins and preserve the requested aggregation and ordering. "
    "Do not invent tables or columns. If the schema cannot answer the question, "
    "return NOT_ANSWERABLE followed by the missing information."
)


@dataclass(frozen=True)
class OpenCodeProvider:
    """SQLProvider using the configured ASU-compatible chat completions endpoint."""

    base_url: str
    api_key: str = field(repr=False)
    model: str = ""
    temperature: float = 0.0
    timeout_seconds: float = 120.0
    provider_name: str = field(default="opencode_chat_completions", init=False)
    is_mock: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("OPENCODE_BASE_URL must be a plain http(s) URL without Markdown or credentials.")
        if parsed.query or parsed.fragment:
            raise ValueError("OPENCODE_BASE_URL must not contain a query or fragment.")
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("Set OPENCODE_API_KEY and COMPLETION_MODEL before generating experiment SQL.")
        if not 0 <= self.temperature <= 2 or self.timeout_seconds <= 0:
            raise ValueError("Temperature must be 0..2 and timeout must be positive.")

    @property
    def api_model(self) -> str:
        """Translate the configured provider prefix to the ASU model-list ID.

        ASU advertises ``devstral2-123b`` in /models, while the user's client
        configuration identifies it as ``openai/devstral2-123b``. This removes
        only that routing prefix; it does not select a different model.
        """
        return self.model.removeprefix("openai/")

    @classmethod
    def from_env(cls, *, model: str | None = None, temperature: float = 0.0) -> "OpenCodeProvider":
        """Read environment only; CLI callers explicitly load their local .env."""
        selected_model = model or os.environ.get("COMPLETION_MODEL") or os.environ.get("OPENCODE_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        return cls(
            base_url=os.environ.get("OPENCODE_BASE_URL", "").strip().rstrip("/"),
            api_key=os.environ.get("OPENCODE_API_KEY", ""), model=selected_model,
            temperature=temperature,
            timeout_seconds=float(os.environ.get("OPENCODE_TIMEOUT_SECONDS", "120")),
        )

    def generate(self, question: str, schema_context: str) -> str:
        """Generate one SQL candidate; both experiment arms use this same prompt."""
        payload = {
            "model": self.api_model, "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Schema:\n{schema_context}\n\nQuestion:\n{question}"},
            ],
            "stream": False, "max_tokens": 2048,
        }
        request = Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                document: dict[str, Any] = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"Configured model request failed (HTTP {exc.code}).") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("Could not reach the configured model endpoint within its timeout.") from None
        try:
            content = document["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ValueError("The model endpoint did not return a chat completion message.") from None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned an empty SQL candidate.")
        candidate = content.strip()
        fenced = re.fullmatch(r"```(?:sql|sqlite)?\s*\n?(.*?)\n?```", candidate, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            candidate = fenced.group(1).strip()
        if candidate.upper().startswith("NOT_ANSWERABLE"):
            raise ValueError("The model reported insufficient schema to answer the question.")
        return candidate


def create_provider(*, model: str | None = None, temperature: float = 0.0) -> OpenCodeProvider:
    """Factory compatible with the schema experiment's provider-factory option."""
    return OpenCodeProvider.from_env(model=model, temperature=temperature)
