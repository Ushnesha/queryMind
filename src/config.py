"""Small typed configuration, with repository-relative paths and no credentials."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value: str | Path) -> Path:
    """Resolve configured relative paths against the repository root."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class DatabaseSettings:
    path: Path = PROJECT_ROOT / "data/analytics.db"


@dataclass(frozen=True)
class ModelSettings:
    temperature: float = 0.0
    provider: str = "mock"


@dataclass(frozen=True)
class OrchestratorSettings:
    max_repairs: int = 3
    max_optimizer_rounds: int = 2


@dataclass(frozen=True)
class SchemaSettings:
    default_mode: str = "neo4j"
    top_k: int = 5


@dataclass(frozen=True)
class EvaluationSettings:
    trace_dir: Path = PROJECT_ROOT / "eval/results"


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    model: ModelSettings = field(default_factory=ModelSettings)
    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)
    schema: SchemaSettings = field(default_factory=SchemaSettings)
    evaluation: EvaluationSettings = field(default_factory=EvaluationSettings)


def load_settings(path: str | Path | None = None) -> Settings:
    """Load YAML defaults; SQLITE_DB and QUERYMIND_PROVIDER override per machine.

    The committed provider stays ``mock`` so tests and credential-free checkouts
    work offline; set ``QUERYMIND_PROVIDER=opencode`` in ``.env`` for live runs.

    This function never opens databases, reads credentials, or calls services.
    Library callers can instead pass a Settings instance to the orchestrator.
    """
    settings_path = resolve_path(path) if path is not None else PROJECT_ROOT / "config/settings.yaml"
    with settings_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("Settings must be a YAML mapping")

    def section(name: str) -> dict[str, Any]:
        value = data.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(f"Settings section {name!r} must be a mapping")
        return value

    database, model = section("database"), section("model")
    routing, schema, evaluation = section("orchestrator"), section("schema"), section("evaluation")
    repairs = int(routing.get("max_repairs", 3))
    rounds = int(routing.get("max_optimizer_rounds", 2))
    top_k = int(schema.get("top_k", 5))
    mode = str(schema.get("default_mode", "neo4j"))
    if not 0 <= repairs <= 3 or not 0 <= rounds <= 2:
        raise ValueError("max_repairs must be 0..3 and max_optimizer_rounds must be 0..2")
    if top_k < 1 or mode not in {"flat", "neo4j"}:
        raise ValueError("schema mode must be flat/neo4j and top_k must be positive")
    return Settings(
        database=DatabaseSettings(resolve_path(os.environ.get("SQLITE_DB") or database.get("path", "data/analytics.db"))),
        model=ModelSettings(
            float(model.get("temperature", 0)),
            str(os.environ.get("QUERYMIND_PROVIDER") or model.get("provider", "mock")).strip(),
        ),
        orchestrator=OrchestratorSettings(repairs, rounds),
        schema=SchemaSettings(mode, top_k),
        evaluation=EvaluationSettings(resolve_path(evaluation.get("trace_dir", "eval/results"))),
    )
