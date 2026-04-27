# Endpoint Index

This index groups the evidence API by audience and purpose.

## Beginner Researcher API

Use these first.

| Goal | Endpoint(s) |
| --- | --- |
| Check service health | `GET /health` |
| Check current identity | `GET /v2/auth/me` |
| Get or create default space | `PUT /v2/spaces/default` |
| Create a named space | `POST /v2/spaces` |
| Start a goal-driven evidence run | `POST /v2/spaces/{space_id}/evidence-runs` |
| Add follow-up instructions | `POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups` |
| Upload text evidence | `POST /v2/spaces/{space_id}/documents/text` |
| Upload PDF evidence | `POST /v2/spaces/{space_id}/documents/pdf` |
| Extract reviewable findings | `POST /v2/spaces/{space_id}/documents/{document_id}/extraction` |
| Review suggestions | `GET /v2/spaces/{space_id}/review-items` |
| Promote or reject suggestions | `POST /v2/spaces/{space_id}/review-items/{item_id}/decision` |
| List evidence sources | `GET /v2/sources` |
| Inspect one evidence source | `GET /v2/sources/{source_key}` |
| Create research plan | `POST /v2/spaces/{space_id}/research-plan` |
| Ask an evidence-map question | `POST /v2/spaces/{space_id}/workflows/evidence-search/tasks` |
| Chat over documents and evidence | `/v2/spaces/{space_id}/chat-sessions/*` |

## Power User API

Use these when you understand the core review flow.

| Goal | Endpoint(s) |
| --- | --- |
| Inspect proposal records directly | `/v2/spaces/{space_id}/proposed-updates/*` |
| Browse evidence-map entities and claims | `/v2/spaces/{space_id}/evidence-map/*` |
| Run connection discovery | `POST /v2/spaces/{space_id}/workflows/connection-discovery/tasks` |
| Explore hypotheses | `POST /v2/spaces/{space_id}/workflows/hypothesis-discovery/tasks` |
| Set up a topic | `POST /v2/spaces/{space_id}/workflows/topic-setup/tasks` |
| Run continuous review | `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks` |
| Run mechanism discovery | `POST /v2/spaces/{space_id}/workflows/mechanism-discovery/tasks` |
| Run evidence curation | `POST /v2/spaces/{space_id}/workflows/evidence-curation/tasks` |
| Create or manage schedules | `/v2/spaces/{space_id}/schedules/*` |
| Use full research workflows | `/v2/spaces/{space_id}/workflows/full-research/*` |
| Search a direct-search source manually | `POST /v2/spaces/{space_id}/sources/{source_key}/searches` |
| Get a source search result | `GET /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}` |
| Hand off one selected source record | `POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs` |

## Runtime And Debug API

Use these to understand what happened inside jobs.

| Goal | Endpoint(s) |
| --- | --- |
| List workflow templates | `GET /v2/workflow-templates` |
| Start a generic task | `POST /v2/spaces/{space_id}/tasks` |
| List or inspect tasks | `GET /v2/spaces/{space_id}/tasks` and `GET /v2/spaces/{space_id}/tasks/{task_id}` |
| Check progress | `GET /v2/spaces/{space_id}/tasks/{task_id}/progress` |
| Check event history | `GET /v2/spaces/{space_id}/tasks/{task_id}/events` |
| Read outputs | `/v2/spaces/{space_id}/tasks/{task_id}/outputs/*` |
| Read working state | `GET /v2/spaces/{space_id}/tasks/{task_id}/working-state` |
| Inspect capabilities | `GET /v2/spaces/{space_id}/tasks/{task_id}/capabilities` |
| Inspect decisions | `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions` |
| Resume a paused task | `POST /v2/spaces/{space_id}/tasks/{task_id}/resume` |
| Approve gated task actions | `/v2/spaces/{space_id}/tasks/{task_id}/approvals/*` |

## Admin And Access API

Use these for identity, API keys, and membership management.

| Goal | Endpoint(s) |
| --- | --- |
| Bootstrap first user | `POST /v2/auth/bootstrap` |
| Create tester user and key | `POST /v2/auth/testers` |
| List API keys | `GET /v2/auth/api-keys` |
| Create API key | `POST /v2/auth/api-keys` |
| Revoke API key | `DELETE /v2/auth/api-keys/{key_id}` |
| Rotate API key | `POST /v2/auth/api-keys/{key_id}/rotate` |
| List space members | `GET /v2/spaces/{space_id}/members` |
| Add member | `POST /v2/spaces/{space_id}/members` |
| Remove member | `DELETE /v2/spaces/{space_id}/members/{user_id}` |
| Update space settings | `PATCH /v2/spaces/{space_id}/settings` |

## Advanced Direct-Write Warning

`POST /v2/spaces/{space_id}/sources/marrvel/ingestion` exists, but normal researcher
workflows should prefer MARRVEL search plus governed review. Direct-write paths
are useful for system-owned or advanced operations, but they are not the best
first API to learn.

Manual source-search and handoff endpoints are also advanced building blocks.
The normal researcher path is now `POST /v2/spaces/{space_id}/evidence-runs`,
which lets the harness create supported source searches, screen saved source
results, and explain selected, skipped, and deferred records before anything
reaches the review gate.

## Source Capability Note

`GET /v2/sources` is the source of truth for which sources can be searched
directly. PubMed, MARRVEL, ClinVar, AlphaFold, UniProt, ClinicalTrials.gov,
MGI, and ZFIN support direct search. DrugBank supports direct search when
`DRUGBANK_API_KEY` is configured. MONDO is a background ontology-grounding
source, while text and PDF are document-capture sources.
Generic source-search responses include `source_capture` metadata so clients can
trace a result to its source, family, query, locator, and provenance. Structured
direct source-search results are stored durably in the Evidence API database and
can be fetched later by id; they are still not trusted graph facts until the
review workflow promotes them.

Use the handoff endpoint when a user selects one captured source-search record
for downstream extraction or normalization. ClinVar and MARRVEL variant records
enter the variant-aware extraction path. PubMed, ClinicalTrials.gov, UniProt,
AlphaFold, DrugBank, MGI, and ZFIN handoffs create durable source documents with
source-capture metadata, normalized record fields, and the original selected
record for auditability. Handoff is idempotent: replaying the same request with
the same idempotency key returns the existing outcome instead of creating
duplicates.
