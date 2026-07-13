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

The current fixture inventory under
`services/artana_evidence_api/tests/fixtures/evidence_selection/` contains only
`med13_congenital_heart_disease` unless new fixture directories are added. Do
not treat the current benchmark as cross-disease, cross-gene, or
production-representative coverage until the inventory is expanded and
documented.

Useful metrics:

- precision: selected records that should have been selected;
- recall: important records that were not missed;
- duplicate rate;
- provenance completeness;
- reviewer agreement;
- high-severity overclaim count;
- categorical explanation adequacy derived from cited findings.

High-severity overclaiming must be zero before calling the harness
production-ready. This is a reviewer/process gate, not just an automated metric:
reviewers must confirm that selected records, explanations, proposals, and
review items do not make clinical, regulatory, causal-truth, or trusted-graph
claims beyond the source evidence.

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
- literal citations, entailment, criteria coverage, and unsupported claims.

Use `docs/validation/evidence-selection-review-template.md` to capture reviewer
labels. The service helper
`artana_evidence_api.evidence_selection_validation.compare_evidence_selection_review`
turns those labels into true positives, false positives, false negatives,
confirmed skips, duplicate counts, precision, recall, categorical explanation
adequacy, and the zero high-severity-overclaim gate. Reviewers provide atomic
categories, literal citations, and written reasoning. Deterministic code derives
all numeric metrics and gates; it does not replace reviewer judgment.

Use `study_type: "selection_relevance"` when the source run does not produce
proposal/review-item ranking decisions. Use
`study_type: "selection_and_review_ranking"` only when both selection and
ranking data exist. A selection-only study must never fabricate ranking rows to
satisfy a schema. `ai_reviewer_simulation` is useful for mechanics and
adversarial tests but cannot pass the production-readiness gate.

Review-ranking calibration is gated separately from per-run precision/recall.
Use
`artana_evidence_api.evidence_selection_validation.evaluate_review_ranking_calibration_gate`
or the runner below to compare prior `ranking_score` values with expert or
shadow-mode outcomes. The gate fails closed unless the review set has enough
decisions, both positive and negative outcomes, both proposal and review-item
sources, no duplicate decision keys, expected calibration error under the
configured threshold, and evidence that scores discriminate positive outcomes
from negative outcomes. Calibration alone is not enough: a constant score can be
well calibrated to the base positive rate while still being useless for review
queue prioritization.

Production calibration studies must also prove study-design coverage. The core
helper and runner default to at least three distinct research goals, at least
three distinct evidence shapes, reviewer IDs on every decision, and a
study-level adjudication note. Missing these fields should fail the gate rather
than producing a production-readiness claim from a narrow or under-reviewed
sample. Goal and evidence-shape counts are normalized before counting, so
whitespace, case, or punctuation variants of the same label do not count as
separate study coverage.

Production-default seed check. This is expected to fail because the seed fixture
is a single-goal mechanics fixture, not production-ready calibration evidence:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json \
  --max-expected-calibration-error 0.15 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-production-default
```

The seed fixture proves the JSON format and threshold mechanics only. It is not
production-representative evidence and must not be used to claim production
readiness by itself. Production use should keep the runner's default `0.05`
expected-calibration-error threshold, `0.70` ROC-AUC threshold, `0.10`
positive-vs-negative mean-score separation threshold, three-goal minimum, and
three-evidence-shape minimum unless a reviewed calibration plan sets stricter
thresholds.

Mechanics-only smoke command. This explicitly relaxes study diversity so the
fixture can prove report rendering and threshold math without claiming
production readiness:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json \
  --max-expected-calibration-error 0.15 \
  --min-distinct-goals 1 \
  --min-distinct-evidence-shapes 1 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-mechanics
```

Production-readiness requires real shadow-mode runs reviewed by human experts
on real research questions. Start with at least three distinct research
questions across different evidence shapes, at least one domain reviewer per
run, and an adjudication note for disagreements or borderline calls. Offline
fixtures and helper metrics are necessary foundation checks, but they are not
evidence that the harness is production ready.

Reviewer packet generation before labels:

```bash
# Set this in the producer environment, not a reviewer workspace.
export ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY=<producer-held-secret>

uv run python scripts/build_evidence_selection_shadow_review_packet.py \
  --run-result path/to/evidence-selection-result.json \
  --study-id <study-id> \
  --output path/to/completed-shadow-review-packet.json
```

The command writes two files: the editable
`completed-shadow-review-packet.json` and the producer-signed
`completed-shadow-review-packet.machine.json`. The packet is explicitly
incomplete: it records the harness-selected, skipped, and deferred candidate
IDs but keeps human labels and ranking outcomes blank. A reviewer may edit only
the first file. Keep the signed machine sidecar under producer control; the
converter rejects a completed packet unless its machine-owned fields and
signature match that sidecar.

After reviewers fill the packet, convert it into the raw source-export writer
inputs:

```bash
uv run python scripts/build_evidence_selection_shadow_review_source_inputs.py \
  --machine-packet path/to/completed-shadow-review-packet.machine.json \
  --packet path/to/completed-shadow-review-packet.json \
  --selection-reviews-output path/to/selection-review-labels.json \
  --review-ranking-output path/to/review-ranking-study.json \
  --adjudication-note "Reviewer adjudicated all labels."
```

The converter defaults to the same `.machine.json` sidecar when
`--machine-packet` is omitted. It fails closed on invalid signatures, changed
machine-owned fields, blank reviewer IDs, blank required ranking outcomes,
missing categorical assessments, missing overclaim findings, citations to
unknown record IDs, or output paths that overwrite either packet. Selection-only
conversion writes one atomic selection file; combined conversion writes paired
outputs so a failed second write does not leave a half-converted review set.

When at least three completed packets are ready, build a strict batch manifest
instead of hand-authoring entry metadata:

```bash
uv run python scripts/build_evidence_selection_shadow_review_study_batch_manifest.py \
  --batch-id <batch-id> \
  --packet path/to/completed-shadow-review-packet-1.json \
  --packet path/to/completed-shadow-review-packet-2.json \
  --packet path/to/completed-shadow-review-packet-3.json \
  --study-evidence-kind real_shadow_review \
  --output path/to/shadow-review-study-batch-manifest.json \
  --source-system artana-shadow-review \
  --export-id-prefix <export-id-prefix> \
  --exported-at 2026-07-07T00:00:00Z \
  --exporter-id <exporter-id> \
  --redaction-statement "No PHI or raw patient text included."
```

Add `--adjudication-note` when any packet has
`study_type: "selection_and_review_ranking"`. It is not required for a
selection-only batch.

`--study-evidence-kind` is mandatory. There is no default to
`real_shadow_review`, so an AI simulation or synthetic fixture cannot be
accidentally relabeled as human review by omission. This field records the
declared origin; signed reviewer attestation remains a separate requirement
before the declaration can be independently proven.

The manifest builder validates each source packet with the same completed-packet
contract as the source-input converter, derives entry IDs and output
subdirectories from packet study IDs, stores packet paths relative to the
manifest, derives unique source-export IDs from the export prefix, and refuses
to overwrite a source packet.

Full expert/shadow study gate:

For a selection-only study, pass `--study-type selection_relevance` to the
source-export and bundle builders and omit all review-ranking paths. The
combined example below uses `selection_and_review_ranking`:

```bash
uv run python scripts/build_evidence_selection_source_exports.py \
  --study-type selection_and_review_ranking \
  --selection-reviews path/to/selection-review-labels.json \
  --review-ranking path/to/review-ranking-study.json \
  --selection-export-output path/to/selection-review-export.json \
  --review-ranking-export-output path/to/review-ranking-export.json \
  --source-system artana-shadow-review \
  --export-id <export-id> \
  --exported-at 2026-07-07T00:00:00Z \
  --exporter-id <exporter-id> \
  --redaction-statement "No PHI or raw patient text included."
```

```bash
uv run python scripts/build_evidence_selection_expert_study_bundle.py \
  --study-id <study-id> \
  --study-type selection_and_review_ranking \
  --study-evidence-kind real_shadow_review \
  --selection-reviews path/to/selection-review-export.json \
  --review-ranking path/to/review-ranking-export.json \
  --output path/to/evidence_selection_expert_study.json
```

The selection-review source export must use
`schema_version: "evidence_selection_review_export.v1"`. The review-ranking
source export must use
`schema_version: "evidence_selection_review_ranking_export.v1"`. Both exports
must carry matching `source_system`, `export_id`, `exported_at`, `exporter_id`,
and `redaction_statement` values. The builder derives the source manifest from
those export fields and rejects identity drift before writing the final bundle.
`exported_at` must be canonical UTC ISO-8601 with a trailing `Z`; timezone-naive
values and offset spellings such as `+00:00` or `+01:00` are rejected so source
identity remains literal and reproducible. Identity text fields are not
trimmed; leading or trailing whitespace is rejected instead of normalized.

```bash
uv run python scripts/run_evidence_selection_expert_study_gate.py \
  --input path/to/evidence_selection_expert_study.json \
  --output-dir reports/evidence_selection_expert_study/<date>-<study-id>
```

This runner combines selection-review precision/recall, reviewer coverage,
deterministically derived explanation adequacy, high-severity overclaim checks,
and, for combined studies, the review-ranking calibration gate above. It also
requires a source manifest with hashed export artifacts, exact selection-review
run IDs, exact required review-ranking decision keys,
and a reviewer roster covering every reviewer ID in the bundle. It fails closed
if a required selection-review, source-manifest, or review-ranking gate is
undercovered or below threshold. The study bundle must
declare `study_evidence_kind: "real_shadow_review"` before it can pass.
Synthetic fixtures remain valid for mechanics testing, but they must not
produce a passing production-style study gate. Every selection review must
include a reviewer ID, a nonblank goal, measurable precision, measurable recall,
and a complete categorical explanation assessment with candidate-bound source
citations.

Batch production-readiness gate:

```bash
uv run python scripts/build_evidence_selection_shadow_review_study_batch.py \
  --manifest path/to/shadow-review-study-batch-manifest.json \
  --output-dir reports/evidence_selection_shadow_review_batch/<date>-<batch-id>
```

The batch gate runs the packet-to-source-export-to-study-bundle-to-study-gate
pipeline for every manifest entry, preserves per-entry gate reports, and writes
aggregate JSON and Markdown reports. It fails closed unless the suite proves
minimum entry count, successful entry rate, zero failed entries, total sample
size, independent source/study identity, cross-batch goal/evidence-shape
diversity, aggregate precision/recall/explanation adequacy, and any required
review-ranking calibration together. Reports expose both
`all_entry_observed_quality` for diagnosis and
`passed_entry_production_quality` for readiness; failed studies are not erased
from the diagnostic view. `--allow-failed-gate` is diagnostic only; it lets reports
be written with exit success but does not make a failed suite production-ready.

## Expert-Review Study

Use a small expert-review study before production rollout.

1. Give the same goal and same source result set to the harness and to one or
   more human reviewers.
2. Ask reviewers to classify relevance, completeness, novelty, provenance,
   uncertainty handling, and overclaiming with cited evidence and explanations.
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
extra confidence before releases or source-gateway changes. When using live
checks, keep secrets out of committed files and prefer focused `-k` filters when
validating one source gateway.
