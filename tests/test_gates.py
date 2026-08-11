from __future__ import annotations

from dataclasses import replace

import pytest

from evalforge.gates import GatePolicy, compare_variants, decide_release
from evalforge.models import AgentTrace, EvaluationResult, VariantSummary


def result(
    trace_id: str,
    scenario_id: str,
    variant: str,
    score: float = 1,
    success: bool = True,
    policy: float = 1,
) -> EvaluationResult:
    return EvaluationResult(
        trace_id, scenario_id, variant, score, 1, policy, 1, 1, score, success, ()
    )


def trace(
    trace_id: str, scenario_id: str, variant: str, latency: float = 100, cost: float = 0.001
) -> AgentTrace:
    return AgentTrace(trace_id, "tenant", scenario_id, variant, "ok", (), latency, cost)


def build_report(samples: int = 4):
    baseline_results = [result(f"b{i}", f"s{i}", "baseline", 0.9) for i in range(samples)]
    candidate_results = [result(f"c{i}", f"s{i}", "candidate", 0.92) for i in range(samples)]
    traces = [trace(f"b{i}", f"s{i}", "baseline") for i in range(samples)]
    traces += [trace(f"c{i}", f"s{i}", "candidate") for i in range(samples)]
    return compare_variants("tenant", baseline_results, candidate_results, traces)


def test_compare_matched_variants() -> None:
    report = build_report()
    assert report.paired_samples == 4
    assert report.score_delta == pytest.approx(0.02)
    assert report.score_delta_ci95 == pytest.approx((0.02, 0.02))
    assert report.baseline.variant == "baseline"


def test_compare_requires_shared_scenario() -> None:
    with pytest.raises(ValueError, match="matched"):
        compare_variants(
            "tenant",
            [result("b", "a", "b")],
            [result("c", "z", "c")],
            [trace("b", "a", "b"), trace("c", "z", "c")],
        )


def test_needs_more_data() -> None:
    decision = decide_release(build_report(), GatePolicy(min_samples=10))
    assert decision.status == "needs_more_data"
    assert decision.checks["sample_size"] is False


def test_healthy_candidate_is_promoted() -> None:
    decision = decide_release(build_report(), GatePolicy(min_samples=1))
    assert decision.status == "promoted"
    assert decision.reasons == ()
    assert decision.to_dict()["status"] == "promoted"


def test_quality_regression_is_blocked() -> None:
    report = replace(build_report(), score_delta_ci95=(-0.2, -0.1))
    decision = decide_release(report, GatePolicy(min_samples=1))
    assert decision.status == "blocked"
    assert decision.checks["score_confidence"] is False


def test_success_regression_is_blocked() -> None:
    report = replace(build_report(), success_delta=-0.5)
    assert decide_release(report, GatePolicy(min_samples=1)).checks["task_success"] is False


@pytest.mark.parametrize(
    "field,value,check",
    [("p95_latency_ms", 9_000, "latency_slo"), ("mean_cost_usd", 3, "cost_slo")],
)
def test_operational_slo_regression_is_blocked(field: str, value: float, check: str) -> None:
    report = build_report()
    candidate = replace(report.candidate, **{field: value})
    decision = decide_release(replace(report, candidate=candidate), GatePolicy(min_samples=1))
    assert decision.checks[check] is False


def test_new_policy_failure_is_blocked() -> None:
    report = build_report()
    candidate = replace(report.candidate, policy_failures=1)
    decision = decide_release(replace(report, candidate=candidate), GatePolicy(min_samples=1))
    assert decision.checks["safety"] is False


def test_policy_can_explicitly_allow_safety_delta() -> None:
    report = build_report()
    candidate = replace(report.candidate, policy_failures=1)
    policy = GatePolicy(min_samples=1, allow_new_policy_failures=True)
    assert decide_release(replace(report, candidate=candidate), policy).checks["safety"] is True


def test_gate_policy_rejects_invalid_sample_size() -> None:
    with pytest.raises(ValueError, match="positive"):
        GatePolicy(min_samples=0)


def test_empty_variant_summary_defaults() -> None:
    report = compare_variants(
        "tenant",
        [result("b", "s", "baseline")],
        [result("c", "s", "candidate")],
        [trace("b", "s", "baseline"), trace("c", "s", "candidate")],
    )
    assert isinstance(report.candidate, VariantSummary)
    assert report.to_dict()["candidate"]["samples"] == 1
