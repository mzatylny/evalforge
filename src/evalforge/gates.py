"""Statistical comparison and release policy engine."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from .models import AgentTrace, EvaluationResult, ExperimentReport, VariantSummary, new_id


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _summary(
    variant: str,
    results: list[EvaluationResult],
    traces: dict[str, AgentTrace],
) -> VariantSummary:
    relevant = [traces[item.trace_id] for item in results]
    return VariantSummary(
        variant=variant,
        samples=len(results),
        success_rate=round(mean(float(item.success) for item in results), 6) if results else 0.0,
        mean_score=round(mean(item.total_score for item in results), 6) if results else 0.0,
        p95_latency_ms=round(_percentile([item.latency_ms for item in relevant], 0.95), 3),
        mean_cost_usd=round(mean(item.cost_usd for item in relevant), 6) if relevant else 0.0,
        policy_failures=sum(item.policy_score == 0.0 for item in results),
    )


def _bootstrap_ci(deltas: list[float], samples: int = 1_000, seed: int = 17) -> tuple[float, float]:
    if not deltas:
        return (0.0, 0.0)
    estimates: list[float] = []
    for sample in range(samples):
        selected: list[float] = []
        for position in range(len(deltas)):
            digest = hashlib.sha256(f"{seed}:{sample}:{position}".encode()).digest()
            selected.append(deltas[int.from_bytes(digest[:8]) % len(deltas)])
        estimates.append(mean(selected))
    estimates.sort()
    low = estimates[int(samples * 0.025)]
    high = estimates[min(samples - 1, int(samples * 0.975))]
    return (round(low, 6), round(high, 6))


def compare_variants(
    tenant_id: str,
    baseline_results: list[EvaluationResult],
    candidate_results: list[EvaluationResult],
    traces: list[AgentTrace],
) -> ExperimentReport:
    trace_map = {trace.id: trace for trace in traces}
    baseline_by_scenario = {item.scenario_id: item for item in baseline_results}
    candidate_by_scenario = {item.scenario_id: item for item in candidate_results}
    shared = sorted(set(baseline_by_scenario) & set(candidate_by_scenario))
    if not shared:
        raise ValueError("baseline and candidate need at least one matched scenario")
    score_deltas = [
        candidate_by_scenario[key].total_score - baseline_by_scenario[key].total_score
        for key in shared
    ]
    success_deltas = [
        float(candidate_by_scenario[key].success) - float(baseline_by_scenario[key].success)
        for key in shared
    ]
    baseline_variant = baseline_results[0].variant if baseline_results else "baseline"
    candidate_variant = candidate_results[0].variant if candidate_results else "candidate"
    return ExperimentReport(
        id=new_id("exp"),
        tenant_id=tenant_id,
        baseline=_summary(baseline_variant, baseline_results, trace_map),
        candidate=_summary(candidate_variant, candidate_results, trace_map),
        paired_samples=len(shared),
        success_delta=round(mean(success_deltas), 6),
        score_delta=round(mean(score_deltas), 6),
        score_delta_ci95=_bootstrap_ci(score_deltas),
    )


@dataclass(frozen=True, slots=True)
class GatePolicy:
    min_samples: int = 30
    max_success_regression: float = 0.02
    max_score_regression: float = 0.02
    max_p95_latency_ms: float = 2_000.0
    max_mean_cost_usd: float = 0.01
    allow_new_policy_failures: bool = False

    def __post_init__(self) -> None:
        if self.min_samples <= 0:
            raise ValueError("minimum sample count must be positive")


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    id: str
    experiment_id: str
    status: str
    checks: dict[str, bool]
    reasons: tuple[str, ...]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_release(report: ExperimentReport, policy: GatePolicy) -> ReleaseDecision:
    checks = {
        "sample_size": report.paired_samples >= policy.min_samples,
        "task_success": report.success_delta >= -policy.max_success_regression,
        "score_confidence": report.score_delta_ci95[0] >= -policy.max_score_regression,
        "latency_slo": report.candidate.p95_latency_ms <= policy.max_p95_latency_ms,
        "cost_slo": report.candidate.mean_cost_usd <= policy.max_mean_cost_usd,
        "safety": policy.allow_new_policy_failures
        or report.candidate.policy_failures <= report.baseline.policy_failures,
    }
    labels = {
        "sample_size": "Collect more paired scenarios before making a release decision.",
        "task_success": "Candidate task success regressed beyond the allowed budget.",
        "score_confidence": "The 95% confidence interval includes a material quality regression.",
        "latency_slo": "Candidate p95 latency exceeds the release SLO.",
        "cost_slo": "Candidate mean cost exceeds the release SLO.",
        "safety": "Candidate introduced new policy violations.",
    }
    reasons = tuple(labels[name] for name, passed in checks.items() if not passed)
    if not checks["sample_size"]:
        status = "needs_more_data"
    else:
        status = "promoted" if all(checks.values()) else "blocked"
    return ReleaseDecision(
        id=new_id("decision"),
        experiment_id=report.id,
        status=status,
        checks=checks,
        reasons=reasons,
        policy=asdict(policy),
    )
