# Security policy

## Supported versions

Security updates are applied to the latest release on `main`.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue
containing exploit details, credentials, prompts, or trace data. Include the affected version,
reproduction steps, impact, and a suggested mitigation if available.

## Operational notes

- Replace the local development API key before any shared or production deployment.
- Never put credentials in a trace, scenario, URL, screenshot, or Git history.
- Keep interactive API documentation disabled in production.
- Treat agent outputs as untrusted content and preserve output encoding in custom dashboards.
- A valid audit hash chain proves internal continuity, not independent non-repudiation. Production
  deployments should sign release decisions using a workload identity.
