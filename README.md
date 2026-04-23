# Artana Evidence Platform

`artana-evidence-platform` is the extraction target for the Artana evidence
services that currently live inside the monorepo.

As of April 23, 2026, this repository is the source of truth for:

- `services/artana_evidence_db`
- `services/artana_evidence_api`

Staging deployments for both services now run from this repository's GitHub
Actions workflows.

The current extracted-repo scope is:

- `services/artana_evidence_db`: standalone governed graph service
- `services/artana_evidence_api`: AI evidence and orchestration service

The previous temporary top-level `src/` runtime package and
`packages/artana_api` SDK surface are no longer present in this checkout.

This repository started in planning-and-tracking mode so the migration could be
executed deliberately rather than as an ad hoc folder copy.

## Current Status

As of April 23, 2026, the extracted services are the active source of truth in
this repository.

Present and verified in the extracted repo:

- `services/artana_evidence_db`
- `services/artana_evidence_api`
- service-relevant `scripts/`, `docs/`, and `tests`
- root extracted-repo tooling such as `Makefile`, `pytest.ini`,
  `.dockerignore`, and local Postgres helpers

The migration cutover is complete:

- M2: graph service standalone unwind complete
- M3: evidence API direct production `src` imports eliminated
- M4: CI and deploy workflows complete; SDK references are deferred outside
  this checkout
- M5: cutover complete, staging verified, monorepo copies deprecated
- M6: temporary `src/` package removed

## Tracking Docs

- [User Guide](docs/user-guide/README.md)
- [Migration Plan](docs/migration-plan.md)
- [Migration Checklist](docs/migration-checklist.md)
- [Graph Release Policy](docs/graph/reference/release-policy.md)
- [Graph Service Release Checklist](docs/graph/reference/release-checklist.md)

## Current Boundaries

Included in this extracted repository:

- `services/artana_evidence_db`
- `services/artana_evidence_api`
- selected `scripts/`, `docs/`, and test assets needed to keep service gates green

Out of scope for this checkout unless requirements change:

- `services/research_inbox`
- `services/research_inbox_runtime`
- `services/frontdoor`
- legacy `src/web`
- `packages/artana_api`
- unrelated monorepo services and infrastructure

## Goal

Get the graph service and evidence API into a dedicated repository with a
working local/dev/test/deploy loop and keep the deployable boundary HTTP-first:
the evidence API calls the graph service by contract instead of packaging graph
implementation internals.

## Evidence Workflow And API Map

In simple terms, this repository supports an evidence-review loop:

```text
Choose topic
  -> Find evidence
  -> Stage proposals
  -> Review proposals
  -> Build graph
  -> Explore graph
  -> Find gaps
  -> Run more searches
  -> Review again
```

The endpoints are mostly organized by resource, but they map to the workflow
like this:

| Step | What you do | Main endpoint(s) | Example for MED13 |
| --- | --- | --- | --- |
| 1. Choose topic | Create or get a research space | `POST /v1/spaces` or `PUT /v1/spaces/default` | Create "MED13 Workspace" |
| 2. Define research plan | Tell the system the research goal and source mix | `POST /v1/spaces/{space_id}/research-init` | "Understand MED13 and cardiomyopathy using PubMed, MARRVEL, and ClinVar" |
| 3. Add your own evidence | Upload text notes or PDFs | `POST /v1/spaces/{space_id}/documents/text` and `POST /v1/spaces/{space_id}/documents/pdf` | Upload a MED13 paper, note, or copied abstract |
| 4. Search sources directly | Run source-specific discovery | `POST /v1/spaces/{space_id}/pubmed/searches` and `POST /v1/spaces/{space_id}/marrvel/searches` | Search MED13 papers or MARRVEL gene panels |
| 5. Extract proposals | Turn documents or evidence into reviewable suggestions | `POST /v1/spaces/{space_id}/documents/{document_id}/extract` | Extract MED13 claims, entities, observations, or variants |
| 6. Review proposals | Have a human approve, reject, or resolve staged work | `GET /v1/spaces/{space_id}/review-queue` and `POST /v1/spaces/{space_id}/review-queue/{item_id}/actions` | Promote strong evidence and reject weak claims |
| 7. Build graph | Approved proposals become trusted graph knowledge | Review action with `{"action": "promote"}` | Add an approved MED13 claim to the graph |
| 8. Explore graph | Browse trusted entities, claims, and evidence | `GET /v1/spaces/{space_id}/graph-explorer/entities`, `GET /v1/spaces/{space_id}/graph-explorer/claims`, and `GET /v1/spaces/{space_id}/graph-explorer/claims/{claim_id}/evidence` | See MED13 claims and supporting evidence |
| 9. Ask questions | Query the graph and documents with AI | `POST /v1/spaces/{space_id}/agents/graph-search/runs` or `POST /v1/spaces/{space_id}/chat-sessions/{session_id}/messages` | Ask "What is the strongest MED13 evidence?" |
| 10. Find gaps and repeat | Keep the research space fresh over time | `POST /v1/spaces/{space_id}/agents/continuous-learning/runs` or `POST /v1/spaces/{space_id}/schedules` | Re-run discovery when new MED13 evidence appears |

The main rule is that the AI can find evidence and create proposals, but the
review queue is the gate between "the system found something" and "this is
trusted graph knowledge." Humans promote or reject proposals before they become
official graph state.

For a first local run, start both backend services with:

```bash
make run-all
```

## Verified Baseline

The following checks have already been run successfully from this repository:

- `make graph-service-checks`
- `make artana-evidence-api-service-checks`
- `make run-graph-service`
- `make run-artana-evidence-api-service`
- Docker runtime builds for both service images
