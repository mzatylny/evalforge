"""Provider-neutral replay harness and deterministic fault injection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .models import AgentTrace, EvaluationResult, Scenario, new_id
from .scoring import Evaluator


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    model: str
    prompt_version: str
    latency_multiplier: float = 1.0
    cost_multiplier: float = 1.0
    output_failure_every: int = 0
    policy_failure_every: int = 0
    tool_failure_every: int = 0


class DeterministicReplayRunner:
    """Local runner that demonstrates the control plane without paid APIs."""

    def run(self, tenant_id: str, scenario: Scenario, variant: Variant, index: int) -> AgentTrace:
        seed = int(hashlib.sha256(f"{scenario.id}:{variant.name}".encode()).hexdigest()[:8], 16)
        jitter = seed % 240
        output_terms = list(scenario.expected_terms)
        violations: tuple[str, ...] = ()
        tools = list(scenario.required_tools)

        if variant.output_failure_every and index % variant.output_failure_every == 0:
            output_terms = output_terms[:-1]
        if variant.policy_failure_every and index % variant.policy_failure_every == 0:
            violations = ("UNTRUSTED_INSTRUCTION_FOLLOWED",)
        if variant.tool_failure_every and index % variant.tool_failure_every == 0 and tools:
            tools = tools[:-1]

        output = "Verified response: " + "; ".join(output_terms)
        return AgentTrace(
            id=new_id("trace"),
            tenant_id=tenant_id,
            scenario_id=scenario.id,
            variant=variant.name,
            output=output,
            tool_calls=tuple(tools),
            latency_ms=round((780 + jitter) * variant.latency_multiplier, 3),
            cost_usd=round((0.0068 + (jitter / 100_000)) * variant.cost_multiplier, 6),
            policy_violations=violations,
            model=variant.model,
            prompt_version=variant.prompt_version,
            metadata={"replay": True, "deterministic_seed": seed},
        )


class FailureReducer:
    """Delta-debug a failing trace to the smallest failure-preserving tool sequence."""

    def __init__(self, evaluator: Evaluator) -> None:
        self.evaluator = evaluator

    def minimize(
        self, trace: AgentTrace, scenario: Scenario
    ) -> tuple[AgentTrace, EvaluationResult]:
        original = self.evaluator.evaluate(trace, scenario)
        if original.success:
            raise ValueError("only failing traces can be minimized")
        target_failures = set(original.failure_codes)
        tools = list(trace.tool_calls)
        cursor = 0
        while cursor < len(tools):
            candidate_tools = tools[:cursor] + tools[cursor + 1 :]
            candidate = AgentTrace(
                id=trace.id,
                tenant_id=trace.tenant_id,
                scenario_id=trace.scenario_id,
                variant=trace.variant,
                output=trace.output,
                tool_calls=tuple(candidate_tools),
                latency_ms=trace.latency_ms,
                cost_usd=trace.cost_usd,
                policy_violations=trace.policy_violations,
                model=trace.model,
                prompt_version=trace.prompt_version,
                created_at=trace.created_at,
                metadata={**trace.metadata, "failure_reduced": True},
            )
            result = self.evaluator.evaluate(candidate, scenario)
            if not result.success and target_failures.issubset(result.failure_codes):
                tools = candidate_tools
            else:
                cursor += 1
        minimized = AgentTrace(
            id=trace.id,
            tenant_id=trace.tenant_id,
            scenario_id=trace.scenario_id,
            variant=trace.variant,
            output=trace.output,
            tool_calls=tuple(tools),
            latency_ms=trace.latency_ms,
            cost_usd=trace.cost_usd,
            policy_violations=trace.policy_violations,
            model=trace.model,
            prompt_version=trace.prompt_version,
            created_at=trace.created_at,
            metadata={**trace.metadata, "failure_reduced": True},
        )
        return minimized, self.evaluator.evaluate(minimized, scenario)
