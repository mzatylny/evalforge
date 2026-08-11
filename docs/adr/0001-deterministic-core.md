# ADR-0001: Keep the release core deterministic and provider-neutral

- Status: Accepted
- Date: 2026-08-11

## Context

Agent evaluation platforms often make a live LLM judge central to their scoring pipeline. That is
flexible, but it makes tests expensive and stochastic, complicates incident reconstruction, and
creates a circular dependency: one model decides whether another model is reliable.

## Decision

The default EvalForge core operates on normalized traces and uses deterministic grading. Provider
clients and optional calibrated judges sit behind adapters. The local demonstration never requires
network access. A release decision stores every policy value and derives uncertainty from matched
scorecards using a seeded paired bootstrap.

## Consequences

- Tests, demos, and incident replay are reproducible.
- The release engine is portable across model and tracing vendors.
- Some semantic quality dimensions require a future judge or human-labelled classifier.
- Judge calibration and provenance become explicit engineering work instead of hidden behaviour.
