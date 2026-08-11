from __future__ import annotations

from dataclasses import replace

import pytest

from evalforge.models import AgentTrace, Scenario
from evalforge.scoring import Evaluator, _ordered_tool_score, normalize


def test_normalize_is_case_and_punctuation_insensitive() -> None:
    assert normalize(" Policy-CITATION! ") == "policy citation"


@pytest.mark.parametrize(
    "actual,required,expected",
    [
        ((), (), 1.0),
        (("a", "b"), ("a", "b"), 1.0),
        (("a", "telemetry", "b"), ("a", "b"), 1.0),
        (("b", "a"), ("a", "b"), 0.5),
        ((), ("a",), 0.0),
    ],
)
def test_ordered_tool_score(
    actual: tuple[str, ...], required: tuple[str, ...], expected: float
) -> None:
    assert _ordered_tool_score(actual, required) == expected


def test_perfect_trace_passes(scenario: Scenario, perfect_trace: AgentTrace) -> None:
    result = Evaluator().evaluate(perfect_trace, scenario)
    assert result.success is True
    assert result.total_score == 1.0
    assert result.failure_codes == ()


def test_output_contract_failure_is_explained(
    scenario: Scenario, perfect_trace: AgentTrace
) -> None:
    result = Evaluator().evaluate(replace(perfect_trace, output="approval required"), scenario)
    assert result.success is False
    assert "OUTPUT_CONTRACT_MISSED" in result.failure_codes


def test_forbidden_output_is_a_policy_failure(
    scenario: Scenario, perfect_trace: AgentTrace
) -> None:
    result = Evaluator().evaluate(replace(perfect_trace, output="secret token"), scenario)
    assert result.policy_score == 0
    assert "POLICY_VIOLATION" in result.failure_codes


def test_explicit_policy_violation_is_hard_failure(
    scenario: Scenario, perfect_trace: AgentTrace
) -> None:
    trace = replace(perfect_trace, policy_violations=("PROMPT_INJECTION",))
    assert Evaluator().evaluate(trace, scenario).success is False


def test_missing_critical_tool_is_hard_failure(
    scenario: Scenario, perfect_trace: AgentTrace
) -> None:
    trace = replace(perfect_trace, tool_calls=("payment.lookup",))
    result = Evaluator().evaluate(trace, scenario)
    assert result.success is False
    assert "TOOL_SEQUENCE_MISSED" in result.failure_codes


def test_usage_budgets_produce_failure_codes(scenario: Scenario, perfect_trace: AgentTrace) -> None:
    trace = replace(perfect_trace, latency_ms=2_000, cost_usd=0.02)
    result = Evaluator().evaluate(trace, scenario)
    assert "LATENCY_BUDGET_EXCEEDED" in result.failure_codes
    assert "COST_BUDGET_EXCEEDED" in result.failure_codes
    assert result.latency_score == 0.5
    assert result.cost_score == 0.5


def test_trace_and_scenario_must_match(scenario: Scenario, perfect_trace: AgentTrace) -> None:
    with pytest.raises(ValueError, match="do not match"):
        Evaluator().evaluate(replace(perfect_trace, scenario_id="different"), scenario)


@pytest.mark.parametrize("threshold", [0, -1, 1.1])
def test_invalid_success_threshold_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        Evaluator(threshold)


def test_zero_usage_is_scored_without_division_error(
    scenario: Scenario, perfect_trace: AgentTrace
) -> None:
    result = Evaluator().evaluate(replace(perfect_trace, latency_ms=0, cost_usd=0), scenario)
    assert result.latency_score == 1
    assert result.cost_score == 1
