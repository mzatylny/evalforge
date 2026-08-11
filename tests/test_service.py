from __future__ import annotations

from evalforge.service import EvalForgeService, demo_scenarios
from evalforge.storage import Storage


def test_demo_suite_has_critical_scenarios() -> None:
    scenarios = demo_scenarios(7)
    assert len(scenarios) == 7
    assert any(item.critical for item in scenarios)
    assert len({item.id for item in scenarios}) == 7


def test_demo_runs_end_to_end_and_blocks_regression() -> None:
    storage = Storage(":memory:")
    outcome = EvalForgeService(storage).run_demo("portfolio")
    assert outcome.report.paired_samples == 40
    assert outcome.report.candidate.mean_cost_usd < outcome.report.baseline.mean_cost_usd
    assert outcome.report.candidate.p95_latency_ms < outcome.report.baseline.p95_latency_ms
    assert outcome.decision.status == "blocked"
    assert len(outcome.results) == 80
    dashboard = EvalForgeService(storage).dashboard("portfolio")
    assert dashboard["audit_chain_valid"] is True
    assert dashboard["counts"]["traces"] == 80
    storage.close()
