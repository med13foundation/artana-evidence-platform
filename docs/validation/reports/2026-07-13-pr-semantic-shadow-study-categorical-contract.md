# Semantic Shadow-Study Categorical Contract Report

Date: 2026-07-13

Branch: `alvaro/evidence-shadow-study-categorical-contract`

## Goal

Make shadow-study evidence measurable without asking an LLM or reviewer to
invent numeric quality scores. Reviewers provide categorical findings,
candidate-bound citations, and explanations. Deterministic code derives
precision, recall, explanation adequacy, overclaim counts, calibration, and
readiness decisions.

## Implemented

- Added a single-purpose categorical review contract package.
- Replaced reviewer-authored explanation scores with explicit yes/no findings,
  citations, and structured high-severity overclaim findings.
- Derived explanation adequacy and overclaim counts deterministically.
- Split `selection_relevance` studies from
  `selection_and_review_ranking` studies across packets, completion, exports,
  bundles, pipelines, batches, reports, and CLIs.
- Prevented selection-only studies from fabricating review-ranking artifacts.
- Required an explicit `study_evidence_kind` at artifact and batch boundaries;
  AI simulations and synthetic fixtures cannot pass production readiness.
- Bound review citations and overclaim findings to immutable candidate IDs.
- Separated all-entry observed quality from passed-entry production quality in
  batch reports.
- Added adversarial tests for unsupported claims, candidate binding, invalid
  study/ranking combinations, explicit evidence origin, and selection-only and
  mixed batch behavior.

## Measurement Rules

- Agents and reviewers emit categories, evidence spans, record IDs, and short
  explanations.
- Deterministic code computes all numeric metrics and pass/fail outcomes.
- Missing or contradictory categorical evidence fails closed.
- Only `real_shadow_review` can contribute to a passing production-style gate.
- Selection quality and ranking calibration remain separate claims.

## Adversarial Review

Fixed in this PR:

- Removed the implicit `real_shadow_review` default from the study pipeline and
  batch manifest builder.
- Rejected `unsupported_material_claim_present: yes` unless at least one
  candidate-bound high-severity overclaim finding is present.
- Added all-selection and mixed-study batch matrix tests.

Required follow-up work:

1. Add signed reviewer identity and attestation so `real_shadow_review` is
   proven rather than caller-declared.
2. Capture immutable canonical source text and verify quoted spans and locators
   against those bytes.
3. Resolve every source-manifest URI at gate time and verify digest and parsed
   payload equality.
4. Publish study artifacts and gate reports as one staged, atomic directory.
5. Surface rollback failures instead of suppressing restoration errors.
6. Apply the same categorical-first contract to ranking outcomes before using
   ranking calibration as trusted product evidence.

## Validation Evidence

- All evidence-selection unit and gate regressions passed.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed across 529 service source files
  and every affected CLI.
- `make artana-evidence-api-service-checks` passed against a fresh migrated
  PostgreSQL database.
- `make service-checks` passed for both backend services, generated contracts,
  boundaries, architecture checks, migrations, and repository tests.
- Repository coverage was 87.24%, above the required 86% floor.

Live external API, running-service endpoint, and real OpenAI-agent tests were
skipped by their existing opt-in environment gates. This PR therefore proves
the categorical contract and orchestration behavior, not live model quality.

## Readiness Conclusion

This change improves evaluation integrity and prevents several false readiness
claims. It does not prove trusted-graph readiness. The next evidence milestone
is a genuinely human-attested, source-verifiable shadow-review batch; the graph
quality claim still depends on live representative cases meeting the existing
precision, recall, linking, specificity, and entailment gates.
