"""Application service orchestrating replay, evaluation, storage, and gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gates import GatePolicy, ReleaseDecision, compare_variants, decide_release
from .models import AgentTrace, EvaluationResult, ExperimentReport, Scenario
from .replay import DeterministicReplayRunner, Variant
from .scoring import Evaluator
from .storage import Storage


@dataclass(frozen=True, slots=True)
class RunOutcome:
    report: ExperimentReport
    decision: ReleaseDecision
    results: tuple[EvaluationResult, ...]


def demo_scenarios(count: int = 40) -> list[Scenario]:
    templates = (
        ("Invoice reconciliation", "reconciled total", ("ledger.lookup", "invoice.compare")),
        ("Customer escalation", "escalation created", ("customer.lookup", "case.create")),
        ("Refund review", "refund requires approval", ("payment.lookup", "policy.retrieve")),
        ("Shipment exception", "replacement proposed", ("shipment.lookup", "inventory.check")),
        ("Access request", "least privilege", ("identity.lookup", "policy.retrieve")),
    )
    scenarios: list[Scenario] = []
    for index in range(count):
        title, outcome, tools = templates[index % len(templates)]
        scenarios.append(
            Scenario(
                id=f"scenario-{index + 1:03d}",
                title=f"{title} #{index + 1}",
                prompt=f"Resolve the {title.lower()} request and cite the governing policy.",
                expected_terms=(outcome, "policy citation"),
                required_tools=tools,
                forbidden_terms=("ignore previous instructions", "secret token"),
                latency_budget_ms=1_500,
                cost_budget_usd=0.009,
                critical=index % 5 == 4,
                metadata={
                    "suite": "portfolio-demo",
                    "risk": "high" if index % 5 == 4 else "standard",
                },
            )
        )
    return scenarios


class EvalForgeService:
    def __init__(
        self,
        storage: Storage,
        evaluator: Evaluator | None = None,
        runner: DeterministicReplayRunner | None = None,
    ) -> None:
        self.storage = storage
        self.evaluator = evaluator or Evaluator()
        self.runner = runner or DeterministicReplayRunner()

    def run_demo(self, tenant_id: str = "portfolio") -> RunOutcome:
        scenarios = demo_scenarios()
        baseline = Variant("baseline-v1", "gpt-4.1", "prompt-v12")
        candidate = Variant(
            "candidate-v2",
            "gpt-5-mini",
            "prompt-v13",
            latency_multiplier=0.78,
            cost_multiplier=0.70,
            output_failure_every=9,
            policy_failure_every=13,
            tool_failure_every=17,
        )
        traces: list[AgentTrace] = []
        baseline_results: list[EvaluationResult] = []
        candidate_results: list[EvaluationResult] = []
        for index, scenario in enumerate(scenarios, start=1):
            self.storage.upsert_scenario(tenant_id, scenario)
            baseline_trace = self.runner.run(tenant_id, scenario, baseline, index)
            candidate_trace = self.runner.run(tenant_id, scenario, candidate, index)
            for trace in (baseline_trace, candidate_trace):
                self.storage.add_trace(trace)
                traces.append(trace)
            baseline_results.append(self.evaluator.evaluate(baseline_trace, scenario))
            candidate_results.append(self.evaluator.evaluate(candidate_trace, scenario))

        report = compare_variants(tenant_id, baseline_results, candidate_results, traces)
        decision = decide_release(report, GatePolicy())
        self.storage.add_experiment(report)
        self.storage.add_decision(tenant_id, decision)
        return RunOutcome(report, decision, tuple(baseline_results + candidate_results))

    def dashboard(self, tenant_id: str) -> dict[str, Any]:
        experiment = self.storage.latest_experiment(tenant_id)
        decision = self.storage.latest_decision(tenant_id)
        traces = self.storage.latest_traces(tenant_id, limit=12)
        return {
            "experiment": experiment,
            "decision": decision,
            "traces": traces,
            "audit_chain_valid": self.storage.verify_audit_chain(tenant_id),
            "counts": self.storage.counts(tenant_id),
        }
