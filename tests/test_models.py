from __future__ import annotations

import pytest

from evalforge.models import AgentTrace, Scenario, new_id, utc_now


def test_ids_are_prefixed_and_unique() -> None:
    first = new_id("trace")
    second = new_id("trace")
    assert first.startswith("trace_")
    assert first != second


def test_utc_now_contains_timezone() -> None:
    assert "+00:00" in utc_now()


@pytest.mark.parametrize("field", ["id", "title", "prompt"])
def test_scenario_rejects_blank_required_fields(field: str) -> None:
    values = {"id": "id", "title": "title", "prompt": "prompt", "expected_terms": ("ok",)}
    values[field] = ""
    with pytest.raises(ValueError, match="required"):
        Scenario(**values)


def test_scenario_requires_expected_term() -> None:
    with pytest.raises(ValueError, match="expected term"):
        Scenario("id", "title", "prompt", ())


@pytest.mark.parametrize("latency,cost", [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_scenario_rejects_nonpositive_budgets(latency: float, cost: float) -> None:
    with pytest.raises(ValueError, match="budgets"):
        Scenario("id", "title", "prompt", ("ok",), latency_budget_ms=latency, cost_budget_usd=cost)


def test_trace_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="required"):
        AgentTrace("", "tenant", "scenario", "v", "", (), 1, 1)


@pytest.mark.parametrize("latency,cost", [(-1, 0), (0, -1)])
def test_trace_rejects_negative_usage(latency: float, cost: float) -> None:
    with pytest.raises(ValueError, match="negative"):
        AgentTrace("id", "tenant", "scenario", "v", "", (), latency, cost)


def test_domain_objects_serialize(scenario: Scenario, perfect_trace: AgentTrace) -> None:
    assert scenario.to_dict()["id"] == scenario.id
    assert perfect_trace.to_dict()["tool_calls"][0] == "payment.lookup"
