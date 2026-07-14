# PR6 Semantic Selector Repeatability Harness

Date: 2026-07-13

Branch: `alvaro/evidence-semantic-pr6-live-repeatability`

Base commit: `d23b1dea194d7fc6f116de84738fdf720c536a71` from merged PR `#148`

## Goal

Measure whether semantic evidence selection is repeatable and whether a newer
candidate judge model creates enough real categorical improvement to justify its
cost and latency. The comparison must use identical frozen source records and
must not consume model-authored confidence or other numeric self-scores.

## Root Cause Addressed

The repository already had a relation-extraction model comparison and one live
semantic-selector evaluation, but no selector-specific repeated-run gate. A
single successful diagnostic could therefore hide run variance, one weak case,
artifact replay, or an unjustified stronger-model choice.

## Implemented Boundaries

- Typed protocol, run, telemetry, summary, disagreement, and adoption contracts.
- Protocol and source-lock digests frozen before model calls.
- Three-run minimum for quality comparison; variance remains diagnostic and
  cannot independently cause adoption.
- Exact fixture, baseline, commit, model, artifact, and execution identity
  binding.
- Reopening and hashing every run artifact before aggregation.
- Deterministic score recomputation from categorical record decisions and the
  frozen fixture.
- Assessment-to-prediction consistency checks.
- Worst-run and minimum per-case precision/recall floors.
- Worst-run and per-case coverage floors plus a hard zero-instability gate.
- Interleaved current/candidate execution to reduce time-order confounding.
- Ledger-derived token, cost, and model-latency observations plus independent
  wall-clock measurement, including failed validation retries.
- Exact terminal-event model binding and a digest over normalized ledger facts.
- Deterministic recomputation of token, cost, latency, and cost-provenance
  aggregates from the embedded terminal events.
- Deterministic adoption policy with fail-closed zero-denominator resource
  ratios and an absolute `10x` candidate cost/latency cap.
- Explicit unavailable calibration and `production_readiness_claim=false`.
- Required merged PR `#148` predecessor, trusted-mainline ancestry, and final
  repository/source-state verification.
- Staged all-or-nothing publication, exact bundled source copies, a complete
  file manifest, in-generation manifest digest, and deterministic bundle
  verifier. Publication uses one directory rename.
- Explicit failure receipts with no plausible partial evidence directory.
- Evidence API CI, lint, type-check, and Makefile wiring.

## Validation To Date

- Post-adversarial semantic, repeatability, telemetry, executor, CLI,
  bundle-atomicity, CI-planner, and Makefile contract tests: `154 passed`.
- Postgres-backed runtime-ledger integration test: passed against an ephemeral
  migrated database.
- Focused Ruff checks: passed.
- Evidence API package mypy: passed over `550` source files.
- New comparison CLI mypy: passed.
- Full `make service-checks`: passed with `87.43%` coverage against the `86%`
  repository floor.

## Adversarial Findings Closed During Implementation

1. Numeric score envelopes could initially disagree with categorical run
   decisions. The gate now recomputes every score from the fixture and decisions.
2. Source-lock and run hashes could initially be self-asserted. The gate now
   recomputes the source lock, reopens every run artifact, verifies its digest,
   and checks all bound fields.
3. Good micro averages could initially hide one weak case. The adoption policy
   now enforces a minimum precision and recall floor for every primary case.
4. Incomplete resource telemetry could initially leave model adoption
   ambiguous. The decision is now explicitly inconclusive without complete
   token, cost, and latency observations.
5. Abstaining on difficult negatives could initially game precision and recall.
   Coverage floors now apply globally and per case.
6. Equal aggregate metrics could hide different decisions across runs. Any
   record-level instability now fails the quality gate.
7. A supplied in-memory fixture could diverge from the hashed source file. The
   executor now loads only verified protocol paths, rehashes them throughout the
   run, and embeds exact source copies.
8. A zero-cost or zero-latency current model could make resource ratios
   undefined and bypass safeguards. Positive-over-zero ratios now fail closed.
9. Validation retries could disappear from execution identity and cost. The
   runner now exposes every attempted Artana run ID and telemetry covers all of
   them.
10. Incremental writes could leave a plausible partial result. Evidence now
    remains staged until the manifest and deterministic verifier pass.
11. The comparison CLI could silently resolve a requested candidate back to the
    default model. A comparison-specific trusted resolver now pins exact enabled
    judge models without weakening production override policy.
12. Aggregate telemetry could be forged independently of its event snapshot.
    Every aggregate and its cost provenance are now recomputed from terminal
    events, and the telemetry model must equal the run model.
13. Absolute paths and symlinks could escape a published bundle. Bundle-context
    artifact references must now be relative and resolve beneath the bundle.
14. A material quality gain could justify an arbitrarily expensive model. The
    frozen policy now applies an absolute resource-ratio cap in both ordinary and
    only-passing-candidate paths.
15. The old publication sequence exposed the directory before its digest anchor.
    The anchor now lives inside the staged generation and one rename publishes
    the complete generation.
16. A clean but stale mainline could satisfy the generic ancestry check. The
    protocol now records and verifies merged PR `#148` commit `d23b1dea` as a
    required predecessor.

## Deliberately Pending

No live model-comparison result is attached yet. PR `#148` is merged, and the
roadmap requires PR6 live evidence to run from that integrated mainline. This
branch must be rebased, fully validated, and then run with current judge
`openai:gpt-5.4-mini` and registered candidate `openai:gpt-5.6-luna`. The live
OpenAI catalog and a minimal Responses API request already confirmed Luna is
available to the configured account.

Even a passing live matrix remains AI-adjudicated diagnostic evidence. It can
support a model configuration choice, but it cannot replace the independent
expert pilot or establish trusted-graph readiness.
