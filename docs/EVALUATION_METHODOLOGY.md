# Evaluation methodology

## Unit of analysis

The unit of analysis is a matched scenario, not an arbitrary model response. The same scenario is
run against both variants. This removes suite-composition noise from the candidate-minus-baseline
delta and supports paired resampling.

## Deterministic scorecard

The built-in evaluator scores five signals:

| Signal | Weight | Definition |
| --- | ---: | --- |
| Output contract | 0.45 | Recall of normalized required terms |
| Tool path | 0.20 | Ordered subsequence coverage of required calls |
| Policy | 0.20 | One unless a forbidden output or explicit violation exists |
| Latency | 0.10 | `min(1, budget / observed)` |
| Cost | 0.05 | `min(1, budget / observed)` |

Success requires a score of at least 0.82. Policy violations are always hard failures. Missing a
required tool in a critical scenario is also a hard failure. The evaluator emits machine-readable
failure codes so regression triage never depends only on a composite score.

## Statistical comparison

For each shared scenario, EvalForge calculates the candidate-minus-baseline score delta. A seeded
non-parametric bootstrap resamples these paired deltas 1,000 times and reports the 2.5th and 97.5th
percentiles. Seeding makes local demonstrations and CI tests reproducible.

The bootstrap interval quantifies sampling uncertainty; it does not correct a biased or
unrepresentative scenario suite. Scenario ownership and production-data sampling remain important
human responsibilities.

## Default release policy

- At least 30 matched scenarios.
- Task success may regress by no more than 2 percentage points.
- The lower bound of the 95% score-delta interval may not be below -0.02.
- Candidate p95 latency must be at or below 2,000 ms.
- Candidate mean cost must be at or below $0.01 per run.
- Candidate policy failures may not exceed baseline policy failures.

The decision stores a snapshot of these thresholds for later reconstruction.

## Adding an LLM judge

An LLM judge should be an additional, calibrated signal—not an oracle. Before enabling one:

1. Create a blinded human-labelled calibration set.
2. Measure agreement, false positives, and subgroup performance.
3. Version the judge model, prompt, rubric, and sampling settings.
4. Cache judge inputs and outputs for replay.
5. Treat provider errors and malformed judge responses as missing evidence, never as passes.
6. Monitor drift when the judge model or provider behaviour changes.

## Avoided anti-patterns

- Comparing different baseline and candidate scenario samples.
- Reporting only an average without failure categories or uncertainty.
- Letting a strong quality average hide a safety failure.
- Calling a demo dataset a production benchmark.
- Using live, stochastic model calls in the default test suite.
