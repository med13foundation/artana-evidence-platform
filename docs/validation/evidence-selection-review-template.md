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
  "goal": ""
}
```

Interpretation:

- `source_kind`: `proposal` or `review_item`.
- `ranking_score`: the production score shown before the reviewer decision.
- `outcome`: `positive` for promoted proposals or resolved review items;
  `negative` for rejected proposals or dismissed review items.
- `item_id`: stable source item ID. Do not duplicate the same source/item pair
  in one calibration study.

Run
`scripts/run_evidence_selection_review_calibration_gate.py` on the collected
decisions before claiming the ranking threshold is ready.

Production-readiness requires real shadow-mode comparisons with human reviewers
on real research questions. Passing the MED13 fixture alone is not enough.
