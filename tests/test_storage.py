from __future__ import annotations

from evalforge.gates import GatePolicy, compare_variants, decide_release
from evalforge.models import AgentTrace, EvaluationResult, Scenario
from evalforge.storage import Storage


def test_scenarios_are_tenant_isolated(scenario: Scenario) -> None:
    storage = Storage(":memory:")
    storage.upsert_scenario("tenant-a", scenario)
    assert storage.get_scenario("tenant-a", scenario.id) == scenario
    assert storage.get_scenario("tenant-b", scenario.id) is None
    assert storage.list_scenarios("tenant-b") == []
    storage.close()


def test_trace_round_trip_and_isolation(perfect_trace: AgentTrace) -> None:
    storage = Storage(":memory:")
    storage.add_trace(perfect_trace)
    assert storage.get_trace("tenant-a", perfect_trace.id) == perfect_trace
    assert storage.get_trace("tenant-b", perfect_trace.id) is None
    storage.close()


def test_audit_chain_is_valid_after_writes(scenario: Scenario, perfect_trace: AgentTrace) -> None:
    storage = Storage(":memory:")
    storage.upsert_scenario("tenant-a", scenario)
    storage.add_trace(perfect_trace)
    assert storage.verify_audit_chain("tenant-a") is True
    assert storage.counts("tenant-a")["audit_events"] == 2
    storage.close()


def test_audit_chain_detects_tampering(scenario: Scenario) -> None:
    storage = Storage(":memory:")
    storage.upsert_scenario("tenant-a", scenario)
    storage._connection.execute("UPDATE audit_events SET action = 'tampered'")
    assert storage.verify_audit_chain("tenant-a") is False
    storage.close()


def test_experiment_and_decision_round_trip() -> None:
    storage = Storage(":memory:")
    baseline_trace = AgentTrace("b", "tenant", "s", "baseline", "ok", (), 100, 0.001)
    candidate_trace = AgentTrace("c", "tenant", "s", "candidate", "ok", (), 90, 0.0008)
    baseline = EvaluationResult("b", "s", "baseline", 1, 1, 1, 1, 1, 1, True, ())
    candidate = EvaluationResult("c", "s", "candidate", 1, 1, 1, 1, 1, 1, True, ())
    report = compare_variants("tenant", [baseline], [candidate], [baseline_trace, candidate_trace])
    decision = decide_release(report, GatePolicy(min_samples=1))
    storage.add_experiment(report)
    storage.add_decision("tenant", decision)
    assert storage.latest_experiment("tenant")["id"] == report.id
    assert storage.latest_decision("tenant")["status"] == "promoted"
    assert storage.latest_experiment("other") is None
    assert storage.latest_decision("other") is None
    storage.close()


def test_latest_traces_is_bounded(perfect_trace: AgentTrace) -> None:
    storage = Storage(":memory:")
    storage.add_trace(perfect_trace)
    assert len(storage.latest_traces("tenant-a", limit=500)) == 1
    assert storage.latest_traces("tenant-b") == []
    storage.close()


def test_persistent_database_creates_parent(tmp_path, scenario: Scenario) -> None:
    database = tmp_path / "nested" / "evalforge.db"
    storage = Storage(str(database))
    storage.upsert_scenario("tenant", scenario)
    storage.close()
    reopened = Storage(str(database))
    assert reopened.get_scenario("tenant", scenario.id) == scenario
    reopened.close()
