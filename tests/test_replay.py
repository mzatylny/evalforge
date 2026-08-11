from __future__ import annotations

from dataclasses import replace

import pytest

from evalforge.replay import DeterministicReplayRunner, FailureReducer, Variant
from evalforge.scoring import Evaluator


def test_replay_is_deterministic_except_trace_identity(scenario) -> None:
    runner = DeterministicReplayRunner()
    variant = Variant("candidate", "model", "prompt")
    first = runner.run("tenant", scenario, variant, 1)
    second = runner.run("tenant", scenario, variant, 1)
    assert first.id != second.id
    assert first.output == second.output
    assert first.latency_ms == second.latency_ms
    assert first.cost_usd == second.cost_usd


def test_fault_injection_is_explicit(scenario) -> None:
    variant = Variant(
        "candidate",
        "model",
        "prompt",
        output_failure_every=2,
        policy_failure_every=2,
        tool_failure_every=2,
    )
    trace = DeterministicReplayRunner().run("tenant", scenario, variant, 2)
    assert "policy citation" not in trace.output
    assert trace.policy_violations
    assert len(trace.tool_calls) == 1


def test_variant_usage_multipliers(scenario) -> None:
    runner = DeterministicReplayRunner()
    base = runner.run("tenant", scenario, Variant("base", "m", "p"), 1)
    efficient = runner.run(
        "tenant",
        scenario,
        Variant("base", "m", "p", latency_multiplier=0.5, cost_multiplier=0.5),
        1,
    )
    assert efficient.latency_ms == pytest.approx(base.latency_ms / 2)
    assert efficient.cost_usd == pytest.approx(base.cost_usd / 2, abs=0.000001)


def test_failure_reducer_removes_irrelevant_tools(scenario, perfect_trace) -> None:
    failing = replace(perfect_trace, policy_violations=("unsafe",))
    minimized, result = FailureReducer(Evaluator()).minimize(failing, scenario)
    assert minimized.tool_calls == ()
    assert result.success is False
    assert "POLICY_VIOLATION" in result.failure_codes


def test_failure_reducer_rejects_success(scenario, perfect_trace) -> None:
    with pytest.raises(ValueError, match="failing"):
        FailureReducer(Evaluator()).minimize(perfect_trace, scenario)
