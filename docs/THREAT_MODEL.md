# Threat model

## Protected assets

- Prompts, outputs, tool names, and metadata contained in traces.
- Scenario suites and expected behaviours.
- Release decisions and the evidence used to produce them.
- Tenant API keys and provider credentials held by external replay adapters.

## Trust boundaries

Untrusted clients cross the HTTP boundary. Agent outputs and tool results are untrusted data even
when they come from an internal runtime. The SQLite file and environment variables are trusted only
to the extent of host controls. Browser-rendered trace content crosses an output-encoding boundary.

## Key threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Cross-tenant evidence access | Tenant derived from API key; every storage read has a tenant predicate | Application bugs; production adapter should add database RLS |
| API-key timing disclosure | Constant-time key comparison | Process-level side channels remain environment-specific |
| Stored XSS from agent output | Dashboard escapes trace fields; restrictive CSP | Future UI components must preserve encoding |
| Oversized payload denial | Pydantic length/count/numeric bounds | Total request size should also be limited at the proxy |
| SQL injection | Bound parameters; dynamic table names come from a fixed allowlist | Schema migrations need the same discipline |
| Audit history modification | Per-tenant SHA-256 hash chain and readiness verification | Hash chaining detects but does not prevent privileged deletion |
| Malicious prompt/tool output | Treated as data, not instructions; forbidden-term and policy signals | External judge adapters need prompt-injection hardening |
| Secret leakage in images/logs | Secrets accepted only through headers/environment; no request-body logging | Operators must configure log redaction |
| Candidate gaming the evaluator | Explicit multiple signals, hidden production-derived suites recommended | Any known fixed benchmark can be overfit |

## Deployment requirements

- Terminate TLS at a trusted proxy and limit request-body size.
- Store keys in a managed secret system and rotate them.
- Run the container without root, capabilities, or a writable root filesystem.
- Encrypt trace storage and backups; apply retention and deletion policy.
- Restrict `/docs` in production (disabled by default).
- Treat a missing or unavailable decision as a failed gate.
