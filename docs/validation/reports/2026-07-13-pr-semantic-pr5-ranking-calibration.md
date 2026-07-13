# PR5 Ranking Calibration And Authority Boundaries

Date: 2026-07-13

Branch: `alvaro/evidence-semantic-pr5-ranking-calibration`

## Goal

Make evidence-selection ranking measurable without allowing agent-authored
numbers, retrieval heuristics, uncalibrated weights, or self-asserted status to
masquerade as production calibration evidence.

## Root Causes Addressed

1. The former study contract treated a bare queue score as both rank and
   probability, so ECE could be calculated over a number with no probabilistic
   meaning.
2. Deterministic retrieval ranking could flow through APIs whose names implied
   governed post-judgment authority.
3. A calibration artifact could label itself `validated` in JSON even though
   the repository only had a diagnostic fitter.
4. The fitter did not bind samples to the frozen training partition, allowing
   held-out leakage in principle.
5. Review staging divided operational rank by ten and stored the result as
   confidence, conflating queue order with a probability-like field.

## Implemented Boundaries

- Agent semantic output remains categorical. Deterministic code maps those
  categories to a versioned operational ranking envelope.
- Retrieval numbers are acquisition-only. Review/proposal staging requires an
  operational rank and rejects retrieval-only candidates.
- Calibrated probabilities are explicit, separate, and diagnostic. ECE is
  unavailable rather than zero when they are missing.
- Only the held-out gate can validate calibration. Input JSON cannot use a
  `validated` probability status.
- Frozen protocols carry a producer HMAC signature. Production gates reject
  missing or altered signatures.
- The diagnostic monotonic fitter requires the exact frozen training-question
  partition, rejects held-out leakage, and verifies the training-set digest.
- Queue confidence is a separate versioned categorical policy with explicit
  `deterministic_weight_not_probability` semantics; it is not derived from the
  operational rank.
- Batch quality aggregation preserves missing ECE as missing and blocks
  combined ranking entries without calibration evidence.

## Adversarial Review

An independent Claude review identified self-validated status, unbound
training partitions, ambiguous retrieval-order APIs, and rank-to-confidence
conversion as actionable defects. Those findings were reproduced against the
code and fixed. Two suggestions were rejected after domain review: evaluation
decisions must remain held-out-only, and human abstention does not excuse a
missing precomputed system probability.

Regression tests now cover:

- rejection of self-authored `validated` probability status;
- held-out samples leaking into fitter training;
- altered producer signatures;
- missing production ECE;
- retrieval-only staging attempts;
- explicit acquisition-only retrieval ordering;
- rank and deterministic queue-confidence separation;
- non-finite numeric values, partition overlap, policy drift, and insufficient
  held-out coverage.

## Validation

- Focused adversarial ranking/calibration and workflow tests: passed.
- Evidence API type check: passed across 536 source files and all governed
  evidence-selection scripts.
- Evidence API service gate: passed after all adversarial fixes, including
  lint, typing across 537 source files, service boundaries, OpenAPI contracts,
  agent-output boundaries, architecture checks, migrations, and the full
  database-backed Evidence API test suite.
- Repository pre-commit: passed all lint and type-check hooks.
- Repository `make service-checks`: passed graph and Evidence API gates with
  aggregate coverage `87.25%` against the required `86%` floor.

## Honest Readiness Statement

This PR prevents false calibration claims and makes future expert evidence
measurable. It does not supply the required real human shadow-review corpus,
does not improve the latest live relation precision or CURIE recovery by
itself, and does not make the trusted graph production-ready. The next proof
step is to collect signed, independently reviewed packets across at least 12
training and 8 held-out research questions, fit on training only, and run the
unchanged held-out gate.
