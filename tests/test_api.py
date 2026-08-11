from __future__ import annotations

from fastapi.testclient import TestClient

from evalforge.api import create_app
from evalforge.config import Settings
from evalforge.storage import Storage

KEY = "abcdefghijklmnop"
HEADERS = {"X-EvalForge-Key": KEY}


def client_for(keys: dict[str, str] | None = None, environment: str = "development"):
    storage = Storage(":memory:")
    settings = Settings(":memory:", keys or {KEY: "tenant-a"}, environment)
    return TestClient(create_app(settings, storage)), storage


def scenario_payload() -> dict:
    return {
        "id": "refund-001",
        "title": "Refund review",
        "prompt": "Review refund and cite policy.",
        "expected_terms": ["approval required", "policy citation"],
        "required_tools": ["payment.lookup", "policy.retrieve"],
        "forbidden_terms": ["secret token"],
        "latency_budget_ms": 1000,
        "cost_budget_usd": 0.01,
        "critical": True,
    }


def test_health_is_public_and_hardened() -> None:
    client, storage = client_for()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in response.headers
    storage.close()


def test_root_serves_dashboard() -> None:
    client, storage = client_for()
    response = client.get("/")
    assert response.status_code == 200
    assert "Agent Release Control Tower" in response.text
    assert client.get("/assets/styles.css").status_code == 200
    storage.close()


def test_missing_and_invalid_keys_are_rejected() -> None:
    client, storage = client_for()
    assert client.get("/ready").status_code == 401
    assert client.get("/ready", headers={"X-EvalForge-Key": "wrong"}).status_code == 401
    storage.close()


def test_scenario_and_trace_workflow() -> None:
    client, storage = client_for()
    created = client.post("/api/v1/scenarios", headers=HEADERS, json=scenario_payload())
    assert created.status_code == 201
    assert client.get("/api/v1/scenarios", headers=HEADERS).json()[0]["id"] == "refund-001"
    trace = {
        "scenario_id": "refund-001",
        "variant": "candidate",
        "output": "Approval required with policy citation.",
        "tool_calls": ["payment.lookup", "policy.retrieve"],
        "latency_ms": 500,
        "cost_usd": 0.005,
        "model": "model-a",
        "prompt_version": "p2",
    }
    ingested = client.post("/api/v1/traces", headers=HEADERS, json=trace)
    assert ingested.status_code == 201
    assert ingested.json()["evaluation"]["success"] is True
    trace_id = ingested.json()["trace"]["id"]
    assert client.get(f"/api/v1/traces/{trace_id}", headers=HEADERS).status_code == 200
    assert client.get("/api/v1/traces/unknown", headers=HEADERS).status_code == 404
    storage.close()


def test_trace_requires_existing_tenant_scenario() -> None:
    client, storage = client_for()
    response = client.post(
        "/api/v1/traces",
        headers=HEADERS,
        json={
            "scenario_id": "missing",
            "variant": "v",
            "output": "",
            "latency_ms": 0,
            "cost_usd": 0,
        },
    )
    assert response.status_code == 404
    storage.close()


def test_strict_schema_rejects_unknown_fields() -> None:
    client, storage = client_for()
    payload = scenario_payload()
    payload["tenant_id"] = "attempted-override"
    assert client.post("/api/v1/scenarios", headers=HEADERS, json=payload).status_code == 422
    storage.close()


def test_tenant_isolation_is_derived_from_key() -> None:
    other_key = "qrstuvwxyz12345"
    client, storage = client_for({KEY: "tenant-a", other_key: "tenant-b"})
    client.post("/api/v1/scenarios", headers=HEADERS, json=scenario_payload())
    other = client.get("/api/v1/scenarios", headers={"X-EvalForge-Key": other_key})
    assert other.json() == []
    storage.close()


def test_demo_dashboard_readiness_and_metrics() -> None:
    client, storage = client_for()
    response = client.post("/api/v1/experiments/demo", headers=HEADERS)
    assert response.status_code == 201
    assert response.json()["decision"]["status"] == "blocked"
    dashboard = client.get("/api/v1/dashboard", headers=HEADERS).json()
    assert dashboard["counts"]["traces"] == 80
    assert dashboard["audit_chain_valid"] is True
    assert client.get("/ready", headers=HEADERS).json()["status"] == "ready"
    metrics = client.get("/metrics", headers=HEADERS)
    assert metrics.status_code == 200
    assert 'resource="traces"} 80' in metrics.text
    storage.close()


def test_docs_are_disabled_in_production() -> None:
    client, storage = client_for(environment="production")
    assert client.get("/docs").status_code == 404
    storage.close()
