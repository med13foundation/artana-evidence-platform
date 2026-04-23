# Endpoint Index

This index groups the evidence API by audience and purpose.

## Beginner Researcher API

Use these first.

| Goal | Endpoint(s) |
| --- | --- |
| Check service health | `GET /health` |
| Check current identity | `GET /v1/auth/me` |
| Get or create default space | `PUT /v1/spaces/default` |
| Create a named space | `POST /v1/spaces` |
| Upload text evidence | `POST /v1/spaces/{space_id}/documents/text` |
| Upload PDF evidence | `POST /v1/spaces/{space_id}/documents/pdf` |
| Extract reviewable findings | `POST /v1/spaces/{space_id}/documents/{document_id}/extract` |
| Review suggestions | `GET /v1/spaces/{space_id}/review-queue` |
| Promote or reject suggestions | `POST /v1/spaces/{space_id}/review-queue/{item_id}/actions` |
| Search PubMed | `POST /v1/spaces/{space_id}/pubmed/searches` |
| Search MARRVEL | `POST /v1/spaces/{space_id}/marrvel/searches` |
| Run multi-source setup | `POST /v1/spaces/{space_id}/research-init` |
| Ask a graph question | `POST /v1/spaces/{space_id}/agents/graph-search/runs` |
| Chat over documents and graph | `/v1/spaces/{space_id}/chat-sessions/*` |

## Power User API

Use these when you understand the core review flow.

| Goal | Endpoint(s) |
| --- | --- |
| Inspect proposal records directly | `/v1/spaces/{space_id}/proposals/*` |
| Browse graph entities and claims | `/v1/spaces/{space_id}/graph-explorer/*` |
| Run graph connection discovery | `POST /v1/spaces/{space_id}/agents/graph-connections/runs` |
| Explore hypotheses | `POST /v1/spaces/{space_id}/agents/hypotheses/runs` |
| Bootstrap a topic | `POST /v1/spaces/{space_id}/agents/research-bootstrap/runs` |
| Run continuous learning | `POST /v1/spaces/{space_id}/agents/continuous-learning/runs` |
| Run mechanism discovery | `POST /v1/spaces/{space_id}/agents/mechanism-discovery/runs` |
| Run governed graph curation | `POST /v1/spaces/{space_id}/agents/graph-curation/runs` |
| Create or manage schedules | `/v1/spaces/{space_id}/schedules/*` |
| Use supervisor workflows | `/v1/spaces/{space_id}/agents/supervisor/*` |

## Runtime And Debug API

Use these to understand what happened inside jobs.

| Goal | Endpoint(s) |
| --- | --- |
| List workflow templates | `GET /v1/harnesses` |
| Start a generic run | `POST /v1/spaces/{space_id}/runs` |
| List or inspect runs | `GET /v1/spaces/{space_id}/runs` and `GET /v1/spaces/{space_id}/runs/{run_id}` |
| Check progress | `GET /v1/spaces/{space_id}/runs/{run_id}/progress` |
| Check event history | `GET /v1/spaces/{space_id}/runs/{run_id}/events` |
| Read artifacts | `/v1/spaces/{space_id}/runs/{run_id}/artifacts/*` |
| Read workspace snapshot | `GET /v1/spaces/{space_id}/runs/{run_id}/workspace` |
| Inspect capabilities | `GET /v1/spaces/{space_id}/runs/{run_id}/capabilities` |
| Inspect policy decisions | `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions` |
| Resume a paused run | `POST /v1/spaces/{space_id}/runs/{run_id}/resume` |
| Approve gated run actions | `/v1/spaces/{space_id}/runs/{run_id}/approvals/*` |

## Admin And Access API

Use these for identity, API keys, and membership management.

| Goal | Endpoint(s) |
| --- | --- |
| Bootstrap first user | `POST /v1/auth/bootstrap` |
| List API keys | `GET /v1/auth/api-keys` |
| Create API key | `POST /v1/auth/api-keys` |
| Revoke API key | `DELETE /v1/auth/api-keys/{key_id}` |
| Rotate API key | `POST /v1/auth/api-keys/{key_id}/rotate` |
| List space members | `GET /v1/spaces/{space_id}/members` |
| Add member | `POST /v1/spaces/{space_id}/members` |
| Remove member | `DELETE /v1/spaces/{space_id}/members/{user_id}` |
| Update space settings | `PATCH /v1/spaces/{space_id}/settings` |

## Advanced Direct-Write Warning

`POST /v1/spaces/{space_id}/marrvel/ingest` exists, but normal researcher
workflows should prefer MARRVEL search plus governed review. Direct-write paths
are useful for system-owned or advanced operations, but they are not the best
first API to learn.
