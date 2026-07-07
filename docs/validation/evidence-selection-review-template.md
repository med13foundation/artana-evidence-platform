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
decisions in one bundle:

```json
{
  "schema_version": "evidence_selection_expert_study.v1",
  "study_id": "",
  "study_evidence_kind": "real_shadow_review",
  "description": "",
  "selection_reviews": [],
  "review_ranking": {
    "schema_version": "evidence_selection_review_ranking_calibration.v1",
    "study_id": "",
    "adjudication_note": "",
    "decisions": []
  },
  "source_manifest": {
    "source_system": "",
    "export_id": "",
    "exported_at": "2026-07-07T00:00:00Z",
    "exporter_id": "",
    "redaction_statement": "",
    "source_artifacts": [
      {
        "artifact_id": "",
        "artifact_kind": "selection_review_export",
        "uri": "",
        "sha256": ""
      },
      {
        "artifact_id": "",
        "artifact_kind": "review_ranking_export",
        "uri": "",
        "sha256": ""
      }
    ],
    "selection_review_run_ids": [],
    "review_ranking_decision_keys": [],
    "reviewer_roster": []
  }
}
```

Run `scripts/run_evidence_selection_expert_study_gate.py` on the bundle before
using the study to support a production-readiness claim. Use
`study_evidence_kind: "synthetic_fixture"` for mechanics fixtures; those bundles
must fail the production-style study gate.

The `source_manifest` must describe the real export used to create the bundle.
Use lowercase 64-character SHA-256 hashes for each source artifact. The
`selection_review_run_ids` list must match the selection reviews exactly. The
`review_ranking_decision_keys` list must use `<source_kind>:<item_id>` and match
the review-ranking decisions exactly. The `reviewer_roster` must contain every
selection-review and review-ranking reviewer ID.

Production-readiness requires real shadow-mode comparisons with human reviewers
on real research questions. Passing the MED13 fixture alone is not enough.
