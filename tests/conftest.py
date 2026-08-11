from __future__ import annotations

import pytest

from evalforge.models import AgentTrace, Scenario


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        id="refund-001",
        title="Refund review",
        prompt="Review the refund and cite policy.",
        expected_terms=("approval required", "policy citation"),
        required_tools=("payment.lookup", "policy.retrieve"),
        forbidden_terms=("secret token",),
        latency_budget_ms=1_000,
        cost_budget_usd=0.01,
        critical=True,
    )


@pytest.fixture
def perfect_trace(scenario: Scenario) -> AgentTrace:
    return AgentTrace(
        id="trace-perfect",
        tenant_id="tenant-a",
        scenario_id=scenario.id,
        variant="baseline",
        output="Approval required. Policy citation: REF-7.",
        tool_calls=("payment.lookup", "telemetry.emit", "policy.retrieve"),
        latency_ms=800,
        cost_usd=0.008,
        model="model-a",
        prompt_version="p1",
    )
