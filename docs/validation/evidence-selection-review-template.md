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
  "explanation_quality_score": 1,
  "high_severity_overclaim_count": 0,
  "reviewer_notes": ""
}
```

Interpretation:

- `false_positive`: the harness selected a record the reviewer would not select.
- `false_negative`: the reviewer selected a record the harness missed.
- `duplicate_suggestion`: the harness suggested the same scientific source
  record again without adding useful new context.
- `explanation_quality_score`: 1 is poor, 5 is excellent.
- `high_severity_overclaim_count`: any clinical, regulatory, causal, or
  graph-truth claim that goes beyond the source evidence. This must be zero as
  a reviewer/process gate before production rollout.

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

For a complete expert/shadow study, store selection reviews and review-ranking
decisions as self-describing source exports. The selection-review export shape
is:

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

The two source exports must have matching `source_system`, `export_id`,
`exported_at`, `exporter_id`, and `redaction_statement` values. The
`exported_at` value must be canonical UTC ISO-8601 with a trailing `Z`, such as
`2026-07-07T00:00:00Z`; timezone-naive values and offset spellings such as
`+00:00` or `+01:00` are rejected. Identity text fields are compared literally
and must not contain leading or trailing whitespace. Build the final study
bundle with:

```bash
uv run python scripts/build_evidence_selection_expert_study_bundle.py \
  --study-id <study-id> \
  --study-evidence-kind real_shadow_review \
  --selection-reviews path/to/selection-review-export.json \
  --review-ranking path/to/review-ranking-export.json \
  --output path/to/evidence-selection-expert-study.json
```

`--source-system`, `--export-id`, `--exported-at`, `--exporter-id`, and
`--redaction-statement` are optional compatibility checks only. When supplied,
they must all be supplied together and must exactly match the identity embedded
in both source exports.

Run `scripts/run_evidence_selection_expert_study_gate.py` on the bundle before
using the study to support a production-readiness claim. Use
`study_evidence_kind: "synthetic_fixture"` for mechanics fixtures; those bundles
must fail the production-style study gate.

The generated `source_manifest` must describe the real export used to create
the bundle. The builder computes lowercase 64-character SHA-256 hashes for each
source artifact from the same bytes it parses. The generated
`selection_review_run_ids` list must match the selection reviews exactly. The
generated `review_ranking_decision_keys` list must use `<source_kind>:<item_id>`
and match the review-ranking decisions exactly. The generated `reviewer_roster`
must contain every selection-review and review-ranking reviewer ID.

Production-readiness requires real shadow-mode comparisons with human reviewers
on real research questions. Passing the MED13 fixture alone is not enough.
