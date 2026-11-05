"""Provider boundary; the starter deliberately uses deterministic offline SQL."""

from __future__ import annotations

import re
from typing import Protocol


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


def get_provider(name: str = "mock") -> SQLProvider:
    """Return the explicitly selected provider; never silently enable network."""
    if name != "mock":
        # TODO(feature/orchestrator): add an OpenAI-compatible provider behind this protocol.
        raise ValueError(f"Provider {name!r} is not implemented; use 'mock' for the starter.")
    return MockProvider()
