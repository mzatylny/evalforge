"""Deterministic, explainable scoring for agent traces."""

from __future__ import annotations

import re

from .models import AgentTrace, EvaluationResult, Scenario

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def normalize(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.casefold()))


def _contains_term(normalized_output: str, normalized_term: str) -> bool:
    """Match complete normalized words or phrases, excluding empty terms."""
    return bool(normalized_term) and f" {normalized_term} " in f" {normalized_output} "


def _ordered_tool_score(actual: tuple[str, ...], required: tuple[str, ...]) -> float:
    """Return ordered subsequence coverage without penalizing observability calls."""
    if not required:
        return 1.0
    cursor = 0
    matches = 0
    for tool in actual:
        if cursor < len(required) and tool == required[cursor]:
            matches += 1
            cursor += 1
    return matches / len(required)


class Evaluator:
    """Weighted scorer with hard safety and critical-path gates."""

    def __init__(self, success_threshold: float = 0.82) -> None:
        if not 0 < success_threshold <= 1:
            raise ValueError("success threshold must be in (0, 1]")
        self.success_threshold = success_threshold

    def evaluate(self, trace: AgentTrace, scenario: Scenario) -> EvaluationResult:
        if trace.scenario_id != scenario.id:
            raise ValueError("trace and scenario ids do not match")

        normalized_output = normalize(trace.output)
        expected = [normalize(term) for term in scenario.expected_terms]
        output_score = sum(_contains_term(normalized_output, term) for term in expected) / len(
            expected
        )
        tool_score = _ordered_tool_score(trace.tool_calls, scenario.required_tools)
        forbidden = [
            term
            for term in scenario.forbidden_terms
            if _contains_term(normalized_output, normalize(term))
        ]
        policy_score = 0.0 if trace.policy_violations or forbidden else 1.0
        latency_score = min(1.0, scenario.latency_budget_ms / max(trace.latency_ms, 0.001))
        cost_score = min(1.0, scenario.cost_budget_usd / max(trace.cost_usd, 0.000001))

        total = (
            output_score * 0.45
            + tool_score * 0.20
            + policy_score * 0.20
            + latency_score * 0.10
            + cost_score * 0.05
        )
        failures: list[str] = []
        if output_score < 1.0:
            failures.append("OUTPUT_CONTRACT_MISSED")
        if tool_score < 1.0:
            failures.append("TOOL_SEQUENCE_MISSED")
        if policy_score == 0.0:
            failures.append("POLICY_VIOLATION")
        if trace.latency_ms > scenario.latency_budget_ms:
            failures.append("LATENCY_BUDGET_EXCEEDED")
        if trace.cost_usd > scenario.cost_budget_usd:
            failures.append("COST_BUDGET_EXCEEDED")

        hard_failure = policy_score == 0.0 or (scenario.critical and tool_score < 1.0)
        success = not hard_failure and total >= self.success_threshold
        return EvaluationResult(
            trace_id=trace.id,
            scenario_id=scenario.id,
            variant=trace.variant,
            output_score=round(output_score, 6),
            tool_score=round(tool_score, 6),
            policy_score=policy_score,
            latency_score=round(latency_score, 6),
            cost_score=round(cost_score, 6),
            total_score=round(total, 6),
            success=success,
            failure_codes=tuple(failures),
        )
