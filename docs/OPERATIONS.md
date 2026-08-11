# Operations runbook

## Service-level indicators

Monitor control-plane availability, trace-ingestion error rate, evaluation duration, replay queue
age, decision counts by status, and audit-chain verification. Agent runtime latency and cost are
release signals, not EvalForge service latency.

## Health model

- `GET /health` proves the process can serve requests and requires no authentication.
- `GET /ready` proves authenticated access to tenant evidence and verifies its audit chain.
- `GET /metrics` exposes tenant-scoped resource counts and audit integrity in Prometheus text format.

Readiness failures should remove the instance from traffic. They should not restart a healthy
process in a loop.

## Release incident: unexpected promotion

1. Stop downstream promotion and capture the decision identifier.
2. Verify the tenant audit chain and the exact gate-policy snapshot.
3. Compare scenario identifiers between baseline and candidate; unmatched evidence must not count.
4. Inspect failure codes and normalized traces, starting with critical scenarios.
5. Roll back the agent release independently of EvalForge.
6. Preserve the database and runtime logs as incident evidence.
7. Add the escaped failure to the versioned scenario suite before re-enabling promotion.

## Audit-chain failure

Treat a failed chain as evidence corruption. Make the tenant read-only, snapshot the database, and
compare it with backups. Do not repair or delete events in place. Restore a trusted snapshot and
replay later events from their authoritative trace source.

## Backup and restore

Use SQLite's online backup API or a filesystem snapshot that includes WAL state. Test restoration
quarterly. Backups contain prompts and agent outputs and therefore require the same access controls,
retention policy, and encryption classification as production traces.

## Secret rotation

API keys are supplied through `EVALFORGE_API_KEYS`. To rotate without downtime, temporarily add the
new tenant/key pair, deploy, move clients, then remove the old pair. Never commit keys to the
repository or place them in URLs.

## Capacity controls

The API bounds strings and list sizes. A production replay worker should additionally enforce
per-tenant concurrency, total token/cost budgets, provider timeouts, and queue quotas. Failures must
produce an explicit incomplete decision, never an implicit pass.
