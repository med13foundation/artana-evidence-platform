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
Each review also declares its complete `candidate_record_ids` universe. All
harness and human decisions, audit-note keys, citations, and overclaim findings
must bind to that universe before the study can be evaluated.

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
shadow-mode outcomes. New studies use the full deterministic
`operational_ranking` envelope; the persisted `ranking_score` column is only a
legacy projection. The gate fails closed unless the review set has enough
decisions, both positive and negative outcomes, both proposal and review-item
sources, no duplicate decision keys, expected calibration error under the
configured threshold, and evidence that deterministic operational weights
discriminate positive outcomes from negative outcomes. Calibration alone is not
enough: a constant probability can be well calibrated to the base positive rate
while still being useless for review queue prioritization.

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
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v2.json \
  --max-expected-calibration-error 0.15 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-production-default
```

The seed fixture proves the v2 operational-ranking format and discrimination
mechanics only. It intentionally has no calibrated probabilities or frozen
partition protocol, so calibration is reported as unavailable and the gate
cannot pass even when diversity thresholds are relaxed. Production use should
keep the runner's default `0.05`
expected-calibration-error threshold, `0.70` ROC-AUC threshold, `0.10`
positive-vs-negative mean-operational-weight separation threshold, three-goal minimum, and
three-evidence-shape minimum unless a reviewed calibration plan sets stricter
thresholds.

Diagnostic smoke command. This relaxes study diversity but still fails because
unavailable calibration cannot support a production claim:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v2.json \
  --max-expected-calibration-error 0.15 \
  --min-distinct-goals 1 \
  --min-distinct-evidence-shapes 1 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-mechanics
```

Production-readiness requires real shadow-mode runs reviewed by human experts
on real research questions. Freeze disjoint partitions before fitting: at least
12 training questions and 8 held-out questions, with all 8 held-out questions
actually represented in the evaluation. Record independent expert labels, at
least three goals and evidence shapes, and an adjudication note for disagreements
or borderline calls. The monotonic fitter must consume exactly the frozen
training-question partition and match its training-set digest; it rejects any
held-out question presented as training data.

Candidate probabilities always carry `calibration_status: "diagnostic"`.
Artifacts cannot declare themselves validated. Validation is the outcome of
the held-out gate after it verifies ECE, discrimination, coverage, policy
identity, and the producer-authenticated frozen protocol. The packet producer
signs that protocol with
`ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY`; altered or hand-authored
unsigned protocols cannot support a production claim.

Operational rank and queue confidence are separate deterministic policies.
The rank orders agent-categorized evidence candidates. The legacy numeric
queue-confidence field is projected from the categorical relevance label by a
versioned policy and is explicitly marked
`deterministic_weight_not_probability`; it is never computed by dividing the
rank or treated as calibration evidence. Offline
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
signature match that sidecar. For combined ranking studies the signed
machine-owned fields include the producer-authenticated calibration protocol.

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

Semantic benchmark independent expert pilot packets:

```bash
export ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY=...
uv run python scripts/build_evidence_selection_expert_pilot_packets.py \
  --protocol scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_protocol_v1.json \
  --output-dir reports/human-shadow-study/semantic-relevance-expert-pilot-v1
```

This command produces separately ordered blinded packets for two reviewer slots
and keeps signed candidate mappings in a machine-only directory. The current
three-question, 33-record protocol is diagnostic and explicitly leaves
production calibration and readiness unavailable. Follow
`docs/validation/evidence-selection-expert-pilot-runbook.md` for distribution,
reviewer independence, categorical findings, adjudication, and attestation.

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
`schema_version: "evidence_selection_review_export.v2"`. The review-ranking
source export must use
`schema_version: "evidence_selection_review_ranking_export.v2"`. Both exports
must carry matching `source_system`, `export_id`, `exported_at`, `exporter_id`,
and `redaction_statement` values. The builder derives the source manifest from
those export fields and rejects identity drift before writing the final bundle.
`exported_at` must be canonical UTC ISO-8601 with a trailing `Z`; timezone-naive
values and offset spellings such as `+00:00` or `+01:00` are rejected so source
identity remains literal and reproducible. Identity text fields are not
trimmed; leading or trailing whitespace is rejected instead of normalized.
Selection-review v1 represented the former numeric explanation contract and is
rejected rather than interpreted as categorical v2 evidence.

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

## Semantic Selector Repeatability And Model Comparison

Run the controlled selector comparison only from a clean commit containing the
declared trusted mainline commit. Both models receive the same frozen source
records from the semantic diagnostic fixture in an interleaved schedule. The
harness freezes its protocol before the first model call and rechecks the commit,
mainline ref, worktree, and source hashes before publication.

```bash
COMMIT="$(git rev-parse HEAD)"
make evidence-selection-semantic-model-comparison \
  EVALUATED_COMMIT="$COMMIT" \
  TRUSTED_MAINLINE_REF=origin/main \
  EVIDENCE_SELECTION_REQUIRED_MAINLINE_COMMIT=d23b1dea194d7fc6f116de84738fdf720c536a71 \
  CURRENT_MODEL=openai:gpt-5.4-mini \
  CANDIDATE_MODEL=openai:gpt-5.6-luna \
  COMPARISON_OUTPUT_DIR=reports/evidence_selection_semantic_model_comparison/<date>-<comparison-id>
```

`CURRENT_MODEL` may be omitted to use the configured default judge model. A
candidate override must resolve to a distinct registered judge model before any
run starts. The command requires the configured Postgres/runtime environment and
an API key, writes to a new output directory, and refuses to overwrite an older
comparison.

The deterministic adoption policy requires worst-run precision, recall, and
decision coverage of at least `0.80`; every case must keep at least `0.70`
decision coverage and every primary case must keep at least `0.70` precision and
recall. Record-level decisions must be stable across runs. Invalid-agent output,
semantic fallback, failed canaries, incomplete telemetry, undefined resource
ratios, or a model mismatch in the Artana event ledger fail closed. A three-run
comparison may adopt only for material worst-run quality improvement. Variance
and disagreement remain diagnostic measurements and cannot independently cause
a model switch. No quality improvement can override the frozen absolute `10x`
candidate cost or latency cap.

Every retry execution is included in token, cost, latency, replay, and model
identity checks. The command writes into a private staging directory, embeds
exact source copies and normalized ledger-event snapshots, recomputes all usage
aggregates from those embedded events, and recomputes the final quality report
from categorical decisions. The content manifest and its digest anchor live in
the same staged generation, which is published with one atomic directory rename.
A failed run leaves a `*.failed.json` receipt and no partial evidence directory.
Committed live bundles belong under
`docs/validation/reports/semantic-model-comparisons/`, which is routed through
the Evidence API CI gate.

This comparison uses AI-adjudicated diagnostic labels. Calibration remains
explicitly unavailable until the independent expert training and held-out
partitions exist, and the comparison never makes a production-readiness or
trusted-graph claim.

## Semantic Benchmark V2 Integrity

Benchmark v2 preserves the v1 fixture and source snapshots byte-for-byte as
historical AI diagnostic evidence. A separate content-addressed packet manifest
binds those bounded snapshots. The v2 fixture may add categorical AI diagnostic
overrides with rationale and literal packet spans, but its schema cannot express
human/expert provenance or agent-authored numeric scores.

Run the deterministic validator with:

```bash
make evidence-selection-semantic-benchmark-v2-check
```

Score eligibility is derived rather than asserted. A future label is eligible
only when the fixture links a `real_shadow_review` bundle that passes the
existing evidence-selection expert-study/provenance gate, that bundle's source
manifest binds the benchmark packet manifest as its adjudication log, its review
run covers the exact case inventory, and a record-level citation resolves to the
bounded packet. The expert-selected set then supplies the categorical expected
label; benchmark code computes all metrics.

AI-only, ambiguous, uncited, or pending-expert records remain visible in JSON
and Markdown but are excluded from adoption metrics. Canary status is
`unavailable` when there are no eligible canary labels; it is never inferred as
passing from AI diagnostic canaries. The initial v2 fixture deliberately has no
linked real-shadow-review bundle, so all 33 records are excluded, including the
defective BRCA1 label and two source-incomplete canaries identified by PR150.

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
