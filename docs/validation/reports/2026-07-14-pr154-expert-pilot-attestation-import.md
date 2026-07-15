# PR154 Expert Pilot Attestation Import

Date: 2026-07-14

Branch: `alvaro/evidence-pr154-attestation`

## Result

PR154 implements the externally authenticated human-review boundary left open
by PR153. It does not create human labels, select a model, claim production
calibration, or claim trusted-graph readiness.

The implementation adds:

- a pre-review evaluation protocol binding all six immutable PR150 live-agent
  runs, exact case/record scope, deterministic formulas, safety scope, and the
  stronger PR150 coverage, per-case, canary, and repeatability gates;
- an issuer-signed Ed25519 study authorization for three distinct verified,
  qualified, conflict-declared human subjects and public keys, with the exact
  issuer trust-anchor fingerprint preserved in the result;
- reviewer-signed categorical first-pass completions with exact packet,
  publication, protocol, chronology, inventory, and literal-span verification;
- deterministic disagreement detection and a model-blinded third-reviewer
  adjudication request;
- adjudicated gold frozen before any model claim is shown to the safety
  reviewer;
- a post-gold categorical claim-safety audit over every selected claim in all
  six runs;
- deterministic human agreement, precision, recall, coverage, per-case,
  canary, repeatability, and overclaim metrics;
- source-owned case/record and primary/canary partitions that registered model
  artifacts cannot redefine;
- atomic no-replace publications for each workflow stage.

## Methodology Corrections

PR153 required zero high-severity overclaims while correctly hiding model claims
from first-pass reviewers. PR154 resolves that mismatch through a separate
post-gold safety phase. It also prevents an expert re-score from weakening PR150
to precision and recall alone.

The six historical runs are treated as pre-existing end-to-end predictions.
Their embedded AI-gold scores are ignored. Experts review complete PubMed
abstracts, whereas those agents consumed sanitized snapshots, so the output is
explicitly a diagnostic re-score and never an automatic model-adoption result.

## Current Honest State

No real reviewer artifacts exist yet. The repository therefore remains at zero
expert-eligible benchmark records. Synthetic cryptographic rehearsals exercise
the implementation only and cannot be imported as expert evidence.

## Validation

Final local branch evidence:

- focused expert-pilot and benchmark regression suite: **44 passed**;
- strict Evidence API typing, including the importer: **passed across 577
  package source files and all registered scripts**;
- architecture size and structure checks: **passed**;
- complete database-backed Evidence API service gate: **passed against a fresh
  migrated ephemeral PostgreSQL database**;
- benchmark truthfulness check: **33 visible, 0 score-eligible, expert study
  pending**.

Repository pre-commit hooks remain a required commit-time gate and may not be
skipped.

Synthetic tests cover forged signatures, packet-publication substitution,
duplicate run bytes, fixture drift, case remapping, canary-role remapping,
incomplete adjudication, incomplete gold, not-assessable safety findings,
repeatability failure, and atomic no-replace publication. Final command results
are recorded in the PR description and CI; none of these rehearsals count as
expert evidence.
