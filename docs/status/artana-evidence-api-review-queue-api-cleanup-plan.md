# Artana Evidence API Review Queue And API Surface Cleanup Plan

Status: Complete and verified
Last updated: 2026-04-21
Primary service: `services/artana_evidence_api`

## Summary

The current `artana_evidence_api` already has a good core workflow:

```text
space -> document -> extract -> review -> chat / larger runs
```

But the public surface has grown several parallel review paths:

- proposals
- run approvals
- inline chat graph-write review
- inline supervisor graph-write review
- `skipped_candidates` returned from document extraction

This plan keeps the current working lower-level APIs, but introduces one
cleaner product-facing review surface so the service stays understandable as we
add first-class review items.

Implementation note:

- the unified `/review-queue` surface is live in `artana_evidence_api`
- review-only items now support canonical actions
  `convert_to_proposal`, `mark_resolved`, and `dismiss`
- `resolve` remains accepted as a compatibility alias for `mark_resolved`
- variant-aware extraction now persists review items directly, and stronger
  rejected relation candidates can be staged as first-class review items when
  they are evidence-backed enough to deserve follow-up
- the Python SDK, docs, examples, and internal review guidance now all default
  to the unified review queue while keeping lower-level proposal and approval
  routes available for advanced callers
- the final verification gate is green across the service and SDK test/check
  suites

## Current Closure Status

What is now in place:

- API-owned `review_item` persistence
- unified `/review-queue` list/get/action routes
- review queue aggregation across proposals, review items, and approvals
- variant-aware extraction persistence of first-class review items
- compatibility preservation for existing `/proposals` and existing extraction
  diagnostic fields
- Python SDK `client.review_queue` surface with typed models and integration
  coverage
- review-queue-first service docs, SDK docs, and examples
- queue-focused regression coverage for meaningful review items versus
  diagnostic-only skipped candidates
- full closure verification through `packages/artana_api` tests and
  `make artana-evidence-api-service-checks`

Closure notes:

- `/proposals` and `/runs/{run_id}/approvals` remain supported as lower-level
  primitives behind the unified queue
- optional live suites still depend on their normal environment flags and live
  services; the required local closure gates for this plan are green

## Why This Plan Exists

From first principles, the system already has three different kinds of things
that need attention:

1. **Decision-ready proposals**
   Ready to promote or reject now.
2. **Important but incomplete review items**
   Worth looking at, but not ready for promotion yet.
3. **Run-owned approval gates**
   A workflow step paused and needs an explicit yes/no decision.

Today those show up through multiple APIs and different response shapes. That
works, but it is harder than it should be for both users and client code.

The goal of this plan is:

- keep the API honest
- keep the main mental model simple
- avoid endpoint sprawl
- keep lower-level primitives available for advanced clients

## Current API Review

Current OpenAPI path count: **76** paths / **84** operations.

Largest route clusters:

- `/agents/*`: 14 paths
- `/runs/*`: 13 paths
- `/chat-sessions/*`: 6 paths
- `/documents/*`: 5 paths
- `/graph-explorer/*`: 5 paths
- `/schedules/*`: 5 paths
- `/proposals/*`: 4 paths

This is not inherently wrong. The problem is not path count alone. The problem
is that the **review surface is split across multiple shapes**.

## Design Principles

### 1. One main review surface

Most users and most product clients should only need one review entry point.

### 2. Honest state types

Do not force incomplete findings into the same bucket as decision-ready
proposals.

### 3. Keep lower-level primitives

Existing `/proposals` and `/runs/{run_id}/approvals` remain valid and useful.
The cleanup is about creating a better top-level product API, not deleting
working internals immediately.

### 4. No feature-owned review subtrees

Do not add:

- `/documents/{id}/review-items`
- `/chat-sessions/{id}/review-items`
- `/agents/.../review-items`

That would spread the same concept across too many places.

### 5. Keep official graph governance separate

These changes stay in `services/artana_evidence_api`.

- `artana_evidence_api` owns orchestration, staged review work, run state, and
  AI-assisted workflow state.
- `artana_evidence_db` continues to own official graph truth and graph-side
  governed mutations.

## Recommended Public API Shape

### Main Product Surface

This is the surface we want users and SDKs to think about first.

| Area | Keep / Add | Why |
| --- | --- | --- |
| `/spaces` | Keep | Project and membership boundary. |
| `/documents` | Keep | Best entry point for evidence-first workflows. |
| `/runs` | Keep | Durable execution, progress, events, artifacts, approvals. |
| `/chat-sessions` | Keep | Grounded assistant workflow. |
| `/review-queue` | Add | Single place for proposals, review items, and approval gates needing attention. |
| `/pubmed/searches`, `/marrvel/searches` | Keep | Clear discovery entry points. |
| `/schedules` | Keep | Continuous learning / recurring work. |

### Lower-Level Or Advanced Surface

These routes remain supported, but should no longer be the default mental model
for new users.

| Area | Keep | Positioning |
| --- | --- | --- |
| `/proposals` | Yes | Lower-level governed proposal API. |
| `/runs/{run_id}/approvals` | Yes | Lower-level run-owned approval API. |
| chat inline candidate review routes | Yes for now | Advanced / compatibility surface. |
| supervisor inline candidate review routes | Yes for now | Advanced / compatibility surface. |
| `/agents/*/runs` | Yes | Advanced orchestration entry points. |
| `/graph-explorer/*` | Yes | Specialist graph inspection surface. |

## New Review Queue Surface

Add one new public endpoint family:

```text
GET  /v1/spaces/{space_id}/review-queue
GET  /v1/spaces/{space_id}/review-queue/{item_id}
POST /v1/spaces/{space_id}/review-queue/{item_id}/actions
```

This becomes the main answer to:

```text
What in this space needs attention right now?
```

## Resource Model

### Review Queue Item

Suggested envelope:

```json
{
  "id": "string",
  "space_id": "string",
  "item_type": "proposal",
  "kind": "candidate_claim",
  "status": "open",
  "title": "string",
  "summary": "string",
  "source_family": "document_extraction",
  "source_ref": "string",
  "run_id": "string",
  "document_id": "string",
  "priority": "medium",
  "next_actions": ["promote", "reject"],
  "linked_resource": {
    "proposal_id": "string"
  },
  "evidence_bundle": [],
  "payload": {},
  "metadata": {},
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Item Types

Use one queue envelope for different underlying resource types:

- `proposal`
- `review_item`
- `approval`

### Proposal vs Review Item vs Approval

#### Proposal

Decision-ready now.

Examples:

- `candidate_claim`
- `entity_candidate`
- `observation_candidate`
- `mechanism_candidate`

Allowed actions:

- `promote`
- `reject`

#### Review Item

Important, but not ready for graph promotion yet.

Examples:

- `phenotype_review_candidate`
- `variant_mapping_review`
- `mechanism_review_candidate`
- `needs_more_evidence`

Allowed actions:

- `convert_to_proposal`
- `dismiss`
- `mark_resolved`

#### Approval

A paused workflow gate tied to one run.

Examples:

- resume-needed curation approval
- run-owned gated mutation approval

Allowed actions:

- `approve`
- `reject`

## What We Keep As Lower-Level APIs

### `/proposals`

Keep:

- `GET /v1/spaces/{space_id}/proposals`
- `GET /v1/spaces/{space_id}/proposals/{proposal_id}`
- `POST /v1/spaces/{space_id}/proposals/{proposal_id}/promote`
- `POST /v1/spaces/{space_id}/proposals/{proposal_id}/reject`

These remain the explicit low-level governed proposal primitives.

### `/runs/{run_id}/approvals`

Keep these as the explicit lower-level run approval primitives.

The review queue should **aggregate** approval work, not replace the underlying
run-specific approval state model immediately.

### Inline Chat / Supervisor Review

Keep for compatibility, but stop treating them as the preferred product review
surface.

Longer term, these should either:

- stage proposals, or
- surface queue items

instead of being their own standalone review world.

## Where Review Items Come From First

The first slice should only migrate the most obvious currently-misaligned
resource:

- `skipped_candidates` from variant-aware document extraction

Specifically:

- `phenotype_review_candidate` becomes a real `review_item`
- selected stronger `rejected_fact` cases may become `review_item`
- weak or purely diagnostic `rejected_fact` entries remain audit-only metadata

Do **not** force every skipped diagnostic into the queue.

## Current Variant-Aware Mapping

### Today

`POST /documents/{document_id}/extract` returns:

- `proposals`
- `skipped_candidates`

### Target

The same extract response should move toward:

- `proposals`
- `review_items`
- optionally `audit_notes`

Internally, the review queue will persist the reviewable items so they can be
listed later outside the immediate extraction response.

## Recommended Endpoint Behavior

### `GET /review-queue`

Purpose:

- list everything that needs attention in one space

Recommended filters:

- `status`
- `item_type`
- `kind`
- `run_id`
- `document_id`
- `source_family`

Recommended default sort:

- newest first, with optional future support for priority ranking

### `GET /review-queue/{item_id}`

Purpose:

- fetch one queue item with its evidence, payload, links, and available actions

### `POST /review-queue/{item_id}/actions`

Purpose:

- one unified action endpoint that dispatches to the correct lower-level logic

Suggested body:

```json
{
  "action": "promote",
  "reason": "Reviewed and approved",
  "metadata": {}
}
```

Dispatch model:

- queue item backed by proposal -> call proposal promotion/rejection path
- queue item backed by approval -> call run approval path
- queue item backed by review item -> update review-item state or convert to proposal

## Persistence Recommendation

Add a dedicated API-owned review item store in `artana_evidence_api`.

Suggested fields:

- `id`
- `space_id`
- `run_id`
- `document_id`
- `item_type`
- `kind`
- `status`
- `title`
- `summary`
- `reason`
- `source_family`
- `source_ref`
- `evidence_bundle`
- `payload`
- `metadata`
- `linked_proposal_id`
- `linked_approval_key`
- `created_at`
- `updated_at`

Start with API-owned persistence, not graph DB persistence.

## What Becomes “Advanced”

In docs and SDK guidance, explicitly label these as advanced/system surfaces:

- `/agents/*/runs`
- inline candidate review endpoints under chat and supervisor
- `/graph-explorer/*`
- raw `/proposals` for low-level callers
- raw `/runs/{run_id}/approvals` for low-level callers

This does not remove them. It just stops making them compete with the main
product workflow.

## Documentation Changes Recommended

### User-facing docs

Keep the simple story:

```text
document -> extract -> review queue -> act -> chat / continue work
```

### API docs

Split route docs into:

1. Main workflow
2. Advanced / specialist workflow

### SDK docs

Prefer a higher-level queue client over exposing only low-level proposal and
approval primitives.

## Implementation Phases

### Phase 1: Review Item Foundation

- add `review_item` persistence
- add schemas and router
- add review queue aggregation over proposals + approvals + review items

### Phase 2: Variant-Aware Extraction Cutover

- emit `review_item` records instead of only `skipped_candidates` for
  `phenotype_review_candidate`
- keep extraction response compatible during transition by still returning the
  current diagnostics shape if needed

### Phase 3: Product Surface Cleanup

- update docs and SDK guidance to make `review-queue` the default review API
- label `/proposals` and inline review routes as advanced

### Phase 4: Wider Adoption

- route more incomplete-but-important findings into review items
- optionally fold selected run approvals into the queue UX more strongly

## Concrete Gap-Closure Checklist

This is the concrete close-out plan required to honestly mark this document
fully done.

### Workstream 1: Public SDK Review Queue Cutover

Goal:

- make the public Python client treat `/review-queue` as the default review
  surface

Implementation checklist:

- [x] add `ArtanaReviewQueueAPI` to `packages/artana_api/src/artana_api/client.py`
- [x] expose `client.review_queue`
- [x] add typed SDK models for:
  - review queue item
  - review queue list response
  - review queue action request
  - review queue action result
- [x] add SDK methods:
  - `list(...)`
  - `get(item_id=...)`
  - `act(item_id=..., action=..., reason=..., metadata=...)`
- [x] keep `client.proposals` intact for lower-level callers
- [x] stop teaching `client.proposals.*` as the default manual review path
- [x] add SDK resource tests for request shapes and response parsing
- [x] add SDK integration coverage for extract -> review_queue -> action

Done when:

- a normal user can complete manual review through `client.review_queue.*`
- the SDK README uses review-queue-first examples
- `client.proposals.*` still works as an advanced surface

### Workstream 2: Docs And OpenAPI Consistency Pass

Goal:

- make every public doc tell the same simple review story

Implementation checklist:

- [x] update `services/artana_evidence_api/docs/api-reference.md` so
  `/review-queue` is the default human review API
- [x] label `/proposals` as lower-level / advanced everywhere it still appears
  as a main path
- [x] label inline chat and supervisor review routes as advanced /
  compatibility-only where they are still documented
- [x] update `services/artana_evidence_api/docs/user-guide.md` so beginner
  workflows use:

  ```text
  document -> extract -> review queue -> act -> continue work
  ```

- [x] update `services/artana_evidence_api/README.md` to match the same mental
  model
- [x] update `packages/artana_api/README.md` to show review-queue-first usage
- [x] regenerate and verify `services/artana_evidence_api/openapi.json`
- [x] refresh OpenAPI freshness tests if endpoint comments or examples change

Done when:

- no beginner-facing doc teaches proposal-first manual review as the normal path
- advanced surfaces remain documented, but clearly framed as advanced
- service docs, SDK docs, and OpenAPI all describe the same workflow

### Workstream 3: Wider Adoption Of Review Items

Goal:

- make more important incomplete findings visible in `/review-queue` as
  first-class review work

Implementation checklist:

- [x] audit extraction and review-producing paths that still emit
  `skipped_candidates` or similar diagnostic-only outputs
- [x] classify each such output into one of:
  - `proposal`
  - `review_item`
  - diagnostic-only skipped metadata
- [x] promote the right incomplete-but-important categories into review items
- [x] keep weak, noisy, or purely audit-only diagnostics out of the queue
- [x] align variant-aware and generic extraction so they follow the same review
  model where practical
- [x] confirm whether selected run approvals need stronger queue metadata or UX
  surfacing; do not duplicate approval state models

Decision rule:

- use `proposal` when the finding is ready for promote/reject now
- use `review_item` when it is important, grounded, but not ready for safe
  promotion
- use skipped diagnostics only when the output is too weak, too incomplete, or
  purely explanatory

Done when:

- important incomplete findings appear in `/review-queue`
- `skipped_candidates` becomes a compatibility or audit channel, not the main
  home for meaningful review work
- the queue remains focused and does not fill with low-value noise

### Workstream 4: Internal Caller And Workflow Cleanup

Goal:

- make internal callers and user-facing guidance point to the same default
  review surface

Implementation checklist:

- [x] audit code paths that generate manual review instructions or links
- [x] update normal user-facing flows to point to `/review-queue`
- [x] keep `/proposals` and `/runs/{run_id}/approvals` available for lower-level
  or specialist callers
- [x] confirm chat, supervisor, and document workflows all describe the same
  main review path
- [x] avoid adding new feature-owned review endpoint subtrees

Done when:

- normal application guidance says "open the review queue"
- lower-level review endpoints remain available without competing with the main
  product story

### Workstream 5: Final Verification And Closure Gate

Goal:

- prove the cleanup is closed across code, docs, SDK, and regression behavior

Implementation checklist:

- [x] run `make artana-evidence-api-service-checks`
- [x] run package tests for `packages/artana_api`
- [x] add or update end-to-end verification for:
  - upload or ingest document
  - extract staged work
  - inspect review queue
  - act on queue item
  - confirm expected proposal / review / graph-visible outcome
- [x] verify existing `/proposals` behavior remains unchanged
- [x] verify existing approval behavior remains unchanged
- [x] verify OpenAPI freshness
- [x] update this plan status and closure notes after all checks pass

Recommended release gate:

```bash
make artana-evidence-api-service-checks
PYTHONPATH=packages/artana_api/src venv/bin/pytest packages/artana_api/tests -q
```

Done when:

- service checks are green
- SDK tests are green
- at least one full review-queue-first end-to-end flow is green
- docs match actual runtime behavior
- this document can be updated to say the plan is fully closed

## Definition Of Done

This plan is fully complete only when all of the following are true:

- `client.review_queue` exists and is the documented default review surface
- service docs and SDK docs both teach review-queue-first manual review
- important incomplete findings are surfaced as `review_item` records where they
  deserve human attention
- `/proposals` remains supported, but clearly advanced
- `/runs/{run_id}/approvals` remains supported, but clearly lower-level
- service and SDK verification gates pass cleanly
- this document status can be updated without caveats

## Non-Goals

This plan does **not**:

- move review-item ownership into `artana_evidence_db`
- remove `/proposals`
- remove `/runs/{run_id}/approvals`
- redesign the graph DB API
- collapse all agent-specific run entry points immediately

## Test Plan

### Unit tests

- review queue item serialization
- action dispatch for proposal-backed items
- action dispatch for approval-backed items
- action dispatch for review-item-backed items
- extraction converts `phenotype_review_candidate` into a stored review item

### Integration tests

- document extraction creates proposals plus review items
- `GET /review-queue` returns proposal-backed and review-item-backed entries
- acting through `/review-queue/{item_id}/actions` calls the correct lower-level
  behavior
- existing `/proposals` routes still work unchanged

### Regression tests

- existing chat inline review endpoints still behave the same
- existing supervisor inline review endpoints still behave the same
- inbox/review clients can still derive “needs attention” state during the
  transition

## Final Recommendation

Add exactly **one** new top-level endpoint family:

```text
/review-queue
```

Keep:

- `/documents`
- `/runs`
- `/chat-sessions`
- `/proposals`
- `/approvals`

But make the product story much simpler:

```text
create evidence -> extract -> open review queue -> take action
```

That gives us a cleaner API, a cleaner UI story, and a truthful place for the
"important but not ready yet" state that currently leaks out as
`skipped_candidates`.
