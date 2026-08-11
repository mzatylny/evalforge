"""Typed domain model shared by the evaluator, storage, and API layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class Scenario:
    """A replayable contract for one agent behaviour."""

    id: str
    title: str
    prompt: str
    expected_terms: tuple[str, ...]
    required_tools: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    latency_budget_ms: float = 2_000.0
    cost_budget_usd: float = 0.01
    critical: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.prompt:
            raise ValueError("scenario id, title, and prompt are required")
        if not self.expected_terms:
            raise ValueError("a scenario needs at least one expected term")
        if self.latency_budget_ms <= 0 or self.cost_budget_usd <= 0:
            raise ValueError("latency and cost budgets must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentTrace:
    """Normalized execution trace independent of an LLM or tracing vendor."""

    id: str
    tenant_id: str
    scenario_id: str
    variant: str
    output: str
    tool_calls: tuple[str, ...]
    latency_ms: float
    cost_usd: float
    policy_violations: tuple[str, ...] = ()
    model: str = "unknown"
    prompt_version: str = "unknown"
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.tenant_id or not self.scenario_id:
            raise ValueError("trace id, tenant id, and scenario id are required")
        if self.latency_ms < 0 or self.cost_usd < 0:
            raise ValueError("trace latency and cost cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Deterministic scorecard for one trace/scenario pair."""

    trace_id: str
    scenario_id: str
    variant: str
    output_score: float
    tool_score: float
    policy_score: float
    latency_score: float
    cost_score: float
    total_score: float
    success: bool
    failure_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VariantSummary:
    variant: str
    samples: int
    success_rate: float
    mean_score: float
    p95_latency_ms: float
    mean_cost_usd: float
    policy_failures: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    id: str
    tenant_id: str
    baseline: VariantSummary
    candidate: VariantSummary
    paired_samples: int
    success_delta: float
    score_delta: float
    score_delta_ci95: tuple[float, float]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
