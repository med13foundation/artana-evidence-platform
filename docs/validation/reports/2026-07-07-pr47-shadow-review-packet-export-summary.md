# PR47 Shadow Review Packet Export Summary

## Run Context

- Branch: `alvaro/evidence-pr47-shadow-review-packet-export`
- Base branch: `alvaro/evidence-pr46-live-onboarding-contract-normalization`
- Scope: Evidence API evidence-selection shadow-review packet generation

## Goal

Make the first human shadow-review collection artifact reproducible from an
evidence-selection result without allowing the system to treat blank reviewer
forms as completed expert evidence.

## Root Cause

PR41 through PR45 made expert/shadow study gates, source provenance, bundle
building, and source exports reproducible. The remaining collection gap was one
step earlier: a run could produce selected/skipped/deferred evidence candidates,
but reviewers still lacked a structured packet that named the exact durable
candidate IDs to label.

Without this packet, teams have to hand-author review inputs, which creates two
risks:

- source-review labels may drift from the run artifact they are supposed to
  evaluate;
- blank forms may accidentally be packaged as expert evidence.

## Code Changes

- Added `artana_evidence_api.evidence_selection.shadow_review_packet`.
- Added strict `evidence_selection_shadow_review_packet.v1` output models.
- Derived candidate IDs from `source_key`, `search_id`, and `record_index`.
- Rejected candidate records that do not have durable source-record IDs.
- Rejected duplicate candidate IDs across selected, skipped, and deferred
  records.
- Added selection-review forms with blank human labels, blank reviewer ID,
  blank explanation score, and blank overclaim count.
- Added review-ranking forms with blank reviewer ID and blank positive/negative
  outcome.
- Classified shadow-mode `would_have_been_selected`/`shadow_decision=selected`
  records as harness selections for review comparison while preserving their
  candidate metadata.
- Added `ranking_score` to evidence-selection proposal and review-item result
  summaries.
- Mapped real `proposals` and `review_items` result artifacts into blank
  review-ranking forms.
- Normalized artifact ranking scores into the strict 0-1 calibration input
  range before writing packet forms.
- Added `production_readiness_claim=false` and explicit
  `completion_required_fields`.
- Added `scripts/build_evidence_selection_shadow_review_packet.py` for
  repeatable packet generation from an evidence-selection result artifact.
- Registered the script with the path-aware CI planner as Evidence API work.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  -q
```

Initial result: four failures because
`artana_evidence_api.evidence_selection.shadow_review_packet` did not exist.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_packet_script_pr_runs_evidence_api_gate \
  -q
```

Initial result: three failures because the packet CLI did not exist and the
path-aware CI planner did not classify the script as Evidence API work.

Adversarial review result:

- BLOCK: shadow-mode recommendations were stored in `deferred_records` by the
  runtime, but the first packet builder treated every deferred record as a
  deferred-only candidate.
- BLOCK: real evidence-selection result artifacts emit `proposals` and
  `review_items`, not `review_ranking_items`; the first CLI adapter therefore
  produced zero ranking forms for real guarded artifacts.
- SHOULD FIX: packet invariants were emitted by the builder but not enforced by
  the schema model.

Fixes added:

- Shadow-mode `shadow_decision=selected` or `would_have_been_selected=true`
  records now populate `harness_selected_record_ids`.
- Runtime result serializers now include `ranking_score` for proposals and
  review items.
- The CLI adapter now maps real `proposals` and `review_items` into blank
  review-ranking forms and normalizes raw source-search scores into 0-1
  calibration scores.
- `EvidenceSelectionShadowReviewPacket` now schema-enforces
  `production_readiness_claim=false` and the exact required-fields contract.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py::test_result_serializers_keep_artifact_payloads_small \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_packet_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_packet_cli_script \
  -q
```

Result: `12 passed`.

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_packet.py \
  scripts/build_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/evidence_selection_result_serialization.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed.

Targeted adversarial re-review result: PASS. The reviewer found no remaining
Critical, Important, or Minor issues after verifying shadow-mode selection
classification, real `proposals`/`review_items` mapping, schema-enforced packet
invariants, and the narrow `ranking_score` serializer expansion.

```bash
make service-checks
```

Result: passed with coverage `87.03%`.

## Interpretation

PR47 closes the packet-generation gap between an evidence-selection run and the
human review labels required by the expert/shadow study gates. It intentionally
does not create completed source exports and does not claim trusted-graph
readiness. A packet remains incomplete until a human reviewer fills the required
selection-review and review-ranking fields.
