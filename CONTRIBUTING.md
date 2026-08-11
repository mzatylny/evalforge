# Contributing

## Development workflow

1. Create a focused change with tests that demonstrate the intended release semantics.
2. Run `make check` locally.
3. Update architecture, methodology, or runbook documentation when a boundary changes.
4. Keep external model calls behind adapters and out of the default test suite.

## Design rules

- Tenant scope must come from authentication, never request data.
- A safety failure cannot be averaged away by other metrics.
- Baseline/candidate comparisons must use matched scenarios.
- Missing evidence never counts as a pass.
- Every gate threshold must be present in the recorded decision.
- Agent outputs are untrusted data at every boundary.

Commits should be small enough to review and describe the engineering outcome in imperative form.
