# Evidence Selection Validation

This validation plan checks whether the evidence-selection harness is useful
for scientific work without overstating what it can prove.

## What Validation Must Show

Validation should show that the harness:

- finds source records that are relevant to the goal;
- skips or defers irrelevant, duplicate, weak, or out-of-scope records;
- preserves source provenance and search IDs;
- explains selected, skipped, and deferred decisions;
- avoids clinical, regulatory, causal, or systematic-review overclaims;
- keeps all graph promotion behind human review.

## Offline Fixture Benchmarks

Offline benchmarks should run without live external APIs. Each fixture should
include a research goal, source-search results, expected selections, expected
skips, known duplicates, and expected proposal/review-item shape.

Useful metrics:

- precision: selected records that should have been selected;
- recall: important records that were not missed;
- duplicate rate;
- provenance completeness;
- reviewer agreement;
- high-severity overclaim count;
- quality of selection and skip reasons.

High-severity overclaiming must be zero before calling the harness
production-ready.

## Shadow-Mode Review

Before broader use, run the harness in shadow mode on real research questions.
In shadow mode it records recommendations without creating source handoffs.

For each run, compare:

- records selected by the harness;
- records selected by a human reviewer;
- records both skipped;
- false positives;
- false negatives;
- duplicate suggestions;
- explanation quality.

Use `docs/validation/evidence-selection-review-template.md` to capture reviewer
labels. The service helper
`artana_evidence_api.evidence_selection_validation.compare_evidence_selection_review`
turns those labels into true positives, false positives, false negatives,
confirmed skips, duplicate counts, precision, recall, explanation quality, and
the zero high-severity-overclaim gate.

## Expert-Review Study

Use a small expert-review study before production rollout.

1. Give the same goal and same source result set to the harness and to one or
   more human reviewers.
2. Ask reviewers to score relevance, completeness, novelty, provenance,
   uncertainty handling, and overclaiming.
3. Record whether the harness saved review time without lowering evidence
   quality.
4. Update benchmark fixtures and selection rules from the reviewer feedback.

This is a validation process, not a one-time automated test.

## Live External API Checks

Live source checks are opt-in because they depend on network access, source
availability, rate limits, and API keys.

Recommended local commands:

```bash
ARTANA_RUN_LIVE_SOURCE_TESTS=1 \
venv/bin/pytest services/artana_evidence_api/tests/integration -q

DRUGBANK_API_KEY=... \
ARTANA_RUN_LIVE_SOURCE_TESTS=1 \
venv/bin/pytest services/artana_evidence_api/tests/integration -q
```

Keep deterministic unit and route tests as the merge gate. Use live tests as
extra confidence before releases or source-gateway changes.
