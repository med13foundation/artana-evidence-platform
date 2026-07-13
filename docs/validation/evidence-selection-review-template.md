# Evidence Selection Review Template

Use this template for shadow-mode or expert-review studies. It records what the
harness selected, what a human reviewer would have selected, and whether the
harness overclaimed.

The current offline fixture inventory contains only
`med13_congenital_heart_disease` unless expanded. Use this template to collect
real shadow-mode human review before making any production-readiness claim.

```json
{
  "run_id": "00000000-0000-0000-0000-000000000000",
  "goal": "",
  "reviewer_id": "",
  "harness_selected_record_ids": [],
  "human_selected_record_ids": [],
  "harness_skipped_record_ids": [],
  "duplicate_suggestion_ids": [],
  "false_positive_notes": {},
  "false_negative_notes": {},
  "explanation_assessment": {
    "literal_citation_present": "yes",
    "citation_entails_claim": "yes",
    "all_required_criteria_addressed": "yes",
    "unsupported_material_claim_present": "no",
    "cited_evidence": [
      {
        "record_id": "",
        "source_locator": "",
        "quoted_text": ""
      }
    ],
    "reviewer_explanation": ""
  },
  "high_severity_overclaim_findings": [],
  "reviewer_notes": ""
}
```

Interpretation:

- `false_positive`: the harness selected a record the reviewer would not select.
- `false_negative`: the reviewer selected a record the harness missed.
- `duplicate_suggestion`: the harness suggested the same scientific source
  record again without adding useful new context.
- `false_positive_notes` and `false_negative_notes`: JSON objects keyed by the
  affected record ID, with a non-blank reviewer explanation as each value. Use
  an empty object when there are no findings of that kind.
- `explanation_assessment`: atomic categorical findings, literal source text,
  and the reviewer's reasoning. Do not author a numeric quality score. The
  service derives `adequate`, `inadequate`, or `unclear` deterministically.
- `citation_entails_claim`: use `unclear` when the cited text does not support a
  confident yes/no judgment. `unclear` never counts as adequate.
- `high_severity_overclaim_findings`: one structured item per clinical,
  regulatory, causal, or graph-truth claim that goes beyond the source
  evidence. The service derives the count; an empty list is required to pass.
- Every cited `record_id`, including citations inside overclaim findings, must
  exist in the producer-signed candidate packet.

The service helper
`artana_evidence_api.evidence_selection_validation.compare_evidence_selection_review`
computes precision, recall, false positives, false negatives, duplicate
suggestions, confirmed skips, and the production overclaim gate from this kind
of reviewer-supplied input. It aggregates the review; it does not decide the
gate without human labels.

For review-ranking calibration, record each decided proposal or review item in
this format:

```json
{
  "source_kind": "proposal",
  "item_id": "",
  "ranking_score": 0.0,
  "outcome": "positive",
  "reviewer_id": "",
  "goal": "",
  "evidence_shape": ""
}
```

Interpretation:

- `source_kind`: `proposal` or `review_item`.
- `ranking_score`: the production score shown before the reviewer decision.
- `outcome`: `positive` for promoted proposals or resolved review items;
  `negative` for rejected proposals or dismissed review items.
- `item_id`: stable source item ID. Do not duplicate the same source/item pair
  in one calibration study.
- `goal`: the reviewed research question used for this decision. Use the real
  study goal, not cosmetic variants to inflate coverage counts.
- `evidence_shape`: the stable evidence category represented by the item, such as
  `variant_disease_relation`, `drug_response_relation`, or
  `fusion_treatment_relation`. Use the reviewed category, not ad hoc synonyms.

Each calibration study must also include a top-level `adjudication_note` that
summarizes disagreements, borderline calls, or why there were none. The
production gate requires at least three distinct goals, at least three distinct
evidence shapes, and reviewer IDs on all decisions. Blank adjudication notes do
not count. Goal and evidence-shape labels are normalized before counting, so
case, spacing, or punctuation variants of the same label do not create fake
study coverage.

Run
`scripts/run_evidence_selection_review_calibration_gate.py` on the collected
decisions before claiming the ranking threshold is ready.

Before collected labels exist, generate a reviewer-facing packet from a saved
evidence-selection result artifact:

```bash
# Set this only in the producer environment.
export ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY=<producer-held-secret>

uv run python scripts/build_evidence_selection_shadow_review_packet.py \
  --run-result path/to/evidence-selection-result.json \
  --study-id <study-id> \
  --output path/to/completed-shadow-review-packet.json
```

The packet uses
`schema_version: "evidence_selection_shadow_review_packet.v2"` and sets
`production_readiness_claim: false`. It is a collection aid, not completed
expert evidence. The command also writes
`completed-shadow-review-packet.machine.json`, containing the producer-signed
machine facts. Keep that sidecar under producer control and let reviewers edit
only `completed-shadow-review-packet.json`. Reviewers must fill the required
human selection labels, reviewer IDs, categorical explanation assessments,
explicit overclaim findings, and, for combined studies, positive/negative
review-ranking outcomes before conversion.

Packets are explicit about study scope:

- `selection_relevance` measures source selection and requires no ranking data.
- `selection_and_review_ranking` measures selection plus downstream ranking and
  requires proposal/review-item outcomes and an adjudication note.

Convert a completed selection-only packet into its raw writer input with:

```bash
uv run python scripts/build_evidence_selection_shadow_review_source_inputs.py \
  --machine-packet path/to/completed-shadow-review-packet.machine.json \
  --packet path/to/completed-shadow-review-packet.json \
  --selection-reviews-output path/to/selection-review-labels.json
```

For a combined selection-and-ranking packet, add the ranking output and
adjudication note:

```bash
uv run python scripts/build_evidence_selection_shadow_review_source_inputs.py \
  --machine-packet path/to/completed-shadow-review-packet.machine.json \
  --packet path/to/completed-shadow-review-packet.json \
  --selection-reviews-output path/to/selection-review-labels.json \
  --review-ranking-output path/to/review-ranking-study.json \
  --adjudication-note "Reviewer adjudicated all labels."
```

This conversion step is still not a readiness claim. It only creates the strict
selection-review label file and review-ranking study file that the source-export
writer consumes next.

For a complete expert/shadow study, store selection reviews and any required
review-ranking decisions as self-describing source exports. The
selection-review export shape is:

```json
{
  "schema_version": "evidence_selection_review_export.v1",
  "source_system": "",
  "export_id": "",
  "exported_at": "2026-07-07T00:00:00Z",
  "exporter_id": "",
  "redaction_statement": "",
  "selection_reviews": []
}
```

The review-ranking export shape is:

```json
{
  "schema_version": "evidence_selection_review_ranking_export.v1",
  "source_system": "",
  "export_id": "",
  "exported_at": "2026-07-07T00:00:00Z",
  "exporter_id": "",
  "redaction_statement": "",
  "review_ranking": {
    "schema_version": "evidence_selection_review_ranking_calibration.v1",
    "study_id": "",
    "adjudication_note": "",
    "decisions": []
  }
}
```

For combined studies, the two source exports must have matching `source_system`, `export_id`,
`exported_at`, `exporter_id`, and `redaction_statement` values. The
`exported_at` value must be canonical UTC ISO-8601 with a trailing `Z`, such as
`2026-07-07T00:00:00Z`; timezone-naive values and offset spellings such as
`+00:00` or `+01:00` are rejected. Identity text fields are compared literally
and must not contain leading or trailing whitespace. Build the source exports
from collected review JSON. For a selection-only study:

```bash
uv run python scripts/build_evidence_selection_source_exports.py \
  --study-type selection_relevance \
  --selection-reviews path/to/selection-review-labels.json \
  --selection-export-output path/to/selection-review-export.json \
  --source-system artana-shadow-review \
  --export-id <export-id> \
  --exported-at 2026-07-07T00:00:00Z \
  --exporter-id <exporter-id> \
  --redaction-statement "No PHI or raw patient text included."
```

For a combined study:

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

Then build the final combined-study bundle with:

```bash
uv run python scripts/build_evidence_selection_expert_study_bundle.py \
  --study-id <study-id> \
  --study-type selection_and_review_ranking \
  --study-evidence-kind real_shadow_review \
  --selection-reviews path/to/selection-review-export.json \
  --review-ranking path/to/review-ranking-export.json \
  --output path/to/evidence-selection-expert-study.json
```

For a selection-only bundle, use `--study-type selection_relevance` and omit
both `--review-ranking` and `--review-ranking-uri`.

`--source-system`, `--export-id`, `--exported-at`, `--exporter-id`, and
`--redaction-statement` are optional compatibility checks only. When supplied,
they must all be supplied together and must exactly match the identity embedded
in both source exports.

Run `scripts/run_evidence_selection_expert_study_gate.py` on the bundle before
using the study to support a production-readiness claim. Use
`study_evidence_kind: "synthetic_fixture"` for mechanics fixtures; those bundles
must fail the production-style study gate. Every artifact and batch command
requires the evidence kind explicitly; none defaults to `real_shadow_review`.
The declaration prevents accidental promotion but does not replace signed
reviewer attestation.

The generated `source_manifest` must describe the real export used to create
the bundle. The builder computes lowercase 64-character SHA-256 hashes for each
source artifact from the same bytes it parses. The generated
`selection_review_run_ids` list must match the selection reviews exactly. The
generated `review_ranking_decision_keys` list must use `<source_kind>:<item_id>`
and match the review-ranking decisions exactly. The generated `reviewer_roster`
must contain every selection-review and review-ranking reviewer ID.

For multi-study production-readiness evidence, build a strict batch manifest
from completed packets before running the batch gate:

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

Add `--adjudication-note` when the batch contains any
`selection_and_review_ranking` packet. Selection-only batches do not require it.

Then run:

```bash
uv run python scripts/build_evidence_selection_shadow_review_study_batch.py \
  --manifest path/to/shadow-review-study-batch-manifest.json \
  --output-dir reports/evidence_selection_shadow_review_batch/<date>-<batch-id>
```

Production-readiness requires real shadow-mode comparisons with human reviewers
on real research questions. Passing the MED13 fixture alone is not enough, and a
single completed packet is not enough.
