"""SQLite persistence with tenant isolation and tamper-evident audit events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .gates import ReleaseDecision
from .models import AgentTrace, ExperimentReport, Scenario, utc_now

COUNT_QUERIES = {
    "scenarios": "SELECT COUNT(*) AS count FROM scenarios WHERE tenant_id = ?",
    "traces": "SELECT COUNT(*) AS count FROM traces WHERE tenant_id = ?",
    "experiments": "SELECT COUNT(*) AS count FROM experiments WHERE tenant_id = ?",
    "decisions": "SELECT COUNT(*) AS count FROM decisions WHERE tenant_id = ?",
    "audit_events": "SELECT COUNT(*) AS count FROM audit_events WHERE tenant_id = ?",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class ScenarioConflictError(ValueError):
    """A stable scenario ID cannot be assigned a different evaluation contract."""


class Storage:
    """Small control-plane store with explicit tenant predicates on every read."""

    def __init__(self, path: str = "evalforge.db") -> None:
        if path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    tenant_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                );
                CREATE TABLE IF NOT EXISTS traces (
                    tenant_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                );
                CREATE INDEX IF NOT EXISTS idx_traces_tenant_scenario
                    ON traces (tenant_id, scenario_id, created_at);
                CREATE TABLE IF NOT EXISTS experiments (
                    tenant_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    tenant_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_tenant_sequence
                    ON audit_events (tenant_id, sequence);
                """
            )

    def close(self) -> None:
        self._connection.close()

    def _append_audit(
        self,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: dict[str, Any],
    ) -> None:
        previous = self._connection.execute(
            """SELECT event_hash FROM audit_events
               WHERE tenant_id = ? ORDER BY sequence DESC LIMIT 1""",
            (tenant_id,),
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "GENESIS"
        created_at = utc_now()
        body = {
            "tenant_id": tenant_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload": payload,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
        event_hash = hashlib.sha256(_canonical(body).encode()).hexdigest()
        self._connection.execute(
            """INSERT INTO audit_events
               (tenant_id, action, resource_type, resource_id, payload,
                previous_hash, event_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tenant_id,
                action,
                resource_type,
                resource_id,
                _canonical(payload),
                previous_hash,
                event_hash,
                created_at,
            ),
        )

    def upsert_scenario(self, tenant_id: str, scenario: Scenario) -> None:
        """Register an immutable scenario; identical retries are idempotent."""
        payload = _canonical(scenario.to_dict())
        with self._lock, self._connection:
            inserted = self._connection.execute(
                """INSERT INTO scenarios (tenant_id, id, payload, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (tenant_id, id)
                   DO NOTHING""",
                (tenant_id, scenario.id, payload, utc_now()),
            )
            if inserted.rowcount == 0:
                existing = self._connection.execute(
                    "SELECT payload FROM scenarios WHERE tenant_id = ? AND id = ?",
                    (tenant_id, scenario.id),
                ).fetchone()
                if json.loads(existing["payload"]) != json.loads(payload):
                    raise ScenarioConflictError(
                        "scenario ID already has a different definition; use a new versioned ID"
                    )
                return
            self._append_audit(
                tenant_id,
                "scenario.created",
                "scenario",
                scenario.id,
                {
                    "scenario": scenario.to_dict(),
                    "definition_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                },
            )

    def add_trace(self, trace: AgentTrace) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO traces
                   (tenant_id, id, scenario_id, variant, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    trace.tenant_id,
                    trace.id,
                    trace.scenario_id,
                    trace.variant,
                    _canonical(trace.to_dict()),
                    trace.created_at,
                ),
            )
            self._append_audit(
                trace.tenant_id, "trace.ingested", "trace", trace.id, {"variant": trace.variant}
            )

    def add_experiment(self, report: ExperimentReport) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO experiments (tenant_id, id, payload, created_at) VALUES (?, ?, ?, ?)",
                (report.tenant_id, report.id, _canonical(report.to_dict()), report.created_at),
            )
            self._append_audit(
                report.tenant_id,
                "experiment.completed",
                "experiment",
                report.id,
                {"paired_samples": report.paired_samples},
            )

    def add_decision(self, tenant_id: str, decision: ReleaseDecision) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO decisions
                   (tenant_id, id, experiment_id, status, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id,
                    decision.id,
                    decision.experiment_id,
                    decision.status,
                    _canonical(decision.to_dict()),
                    utc_now(),
                ),
            )
            self._append_audit(
                tenant_id,
                "release.decided",
                "decision",
                decision.id,
                {"status": decision.status},
            )

    def list_scenarios(self, tenant_id: str) -> list[Scenario]:
        rows = self._connection.execute(
            "SELECT payload FROM scenarios WHERE tenant_id = ? ORDER BY id", (tenant_id,)
        ).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["payload"])
            item["expected_terms"] = tuple(item["expected_terms"])
            item["required_tools"] = tuple(item["required_tools"])
            item["forbidden_terms"] = tuple(item["forbidden_terms"])
            result.append(Scenario(**item))
        return result

    def get_scenario(self, tenant_id: str, scenario_id: str) -> Scenario | None:
        row = self._connection.execute(
            "SELECT payload FROM scenarios WHERE tenant_id = ? AND id = ?", (tenant_id, scenario_id)
        ).fetchone()
        if row is None:
            return None
        item = json.loads(row["payload"])
        item["expected_terms"] = tuple(item["expected_terms"])
        item["required_tools"] = tuple(item["required_tools"])
        item["forbidden_terms"] = tuple(item["forbidden_terms"])
        return Scenario(**item)

    def get_trace(self, tenant_id: str, trace_id: str) -> AgentTrace | None:
        row = self._connection.execute(
            "SELECT payload FROM traces WHERE tenant_id = ? AND id = ?", (tenant_id, trace_id)
        ).fetchone()
        if row is None:
            return None
        item = json.loads(row["payload"])
        item["tool_calls"] = tuple(item["tool_calls"])
        item["policy_violations"] = tuple(item["policy_violations"])
        return AgentTrace(**item)

    def latest_experiment(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT payload FROM experiments WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def latest_decision(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT payload FROM decisions WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def latest_traces(self, tenant_id: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 100)
        rows = self._connection.execute(
            "SELECT payload FROM traces WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, safe_limit),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def verify_audit_chain(self, tenant_id: str) -> bool:
        rows = self._connection.execute(
            "SELECT * FROM audit_events WHERE tenant_id = ? ORDER BY sequence", (tenant_id,)
        ).fetchall()
        previous_hash = "GENESIS"
        for row in rows:
            body = {
                "tenant_id": row["tenant_id"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "payload": json.loads(row["payload"]),
                "previous_hash": row["previous_hash"],
                "created_at": row["created_at"],
            }
            expected = hashlib.sha256(_canonical(body).encode()).hexdigest()
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                return False
            previous_hash = row["event_hash"]
        return True

    def counts(self, tenant_id: str) -> dict[str, int]:
        values: dict[str, int] = {}
        for table, query in COUNT_QUERIES.items():
            row = self._connection.execute(query, (tenant_id,)).fetchone()
            values[table] = int(row["count"])
        return values
