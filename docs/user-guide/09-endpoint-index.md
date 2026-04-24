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
| Upload text evidence | `POST /v2/spaces/{space_id}/documents/text` |
| Upload PDF evidence | `POST /v2/spaces/{space_id}/documents/pdf` |
| Extract reviewable findings | `POST /v2/spaces/{space_id}/documents/{document_id}/extraction` |
| Review suggestions | `GET /v2/spaces/{space_id}/review-items` |
| Promote or reject suggestions | `POST /v2/spaces/{space_id}/review-items/{item_id}/decision` |
| Search PubMed | `POST /v2/spaces/{space_id}/sources/pubmed/searches` |
| Search MARRVEL | `POST /v2/spaces/{space_id}/sources/marrvel/searches` |
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
