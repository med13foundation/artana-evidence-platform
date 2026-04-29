# Workflow Overview

The platform is easiest to understand as a loop.

```text
Choose topic
  -> Start evidence run
  -> Harness selects useful source records
  -> Selected source records become reviewable evidence inputs
  -> Review proposals
  -> Build graph
  -> Explore graph
  -> Find gaps
  -> Add follow-up instructions
  -> Review again
```

## Endpoint Map

| Step | What you do | Main endpoint(s) | Example for MED13 |
| --- | --- | --- | --- |
| 1. Choose topic | Create or get a research space | `POST /v2/spaces` or `PUT /v2/spaces/default` | Create "MED13 Workspace" |
| 2. Start evidence run | Tell the harness the goal, instructions, and review mode | `POST /v2/spaces/{space_id}/evidence-runs` | "Find evidence linking MED13 variants to congenital heart disease" |
| 3. Review proposals | Have a human approve, reject, or resolve staged work | `GET /v2/spaces/{space_id}/review-items` and `POST /v2/spaces/{space_id}/review-items/{item_id}/decision` | Promote strong evidence and reject weak claims |
| 4. Build graph | Approved proposals become trusted graph knowledge | Review action with `{"action": "promote"}` | Add an approved MED13 claim to the graph |
| 5. Explore graph | Browse trusted entities, claims, and evidence | `GET /v2/spaces/{space_id}/evidence-map/entities`, `GET /v2/spaces/{space_id}/evidence-map/claims`, and `GET /v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence` | See MED13 claims and supporting evidence |
| 6. Ask questions | Query the graph and documents with AI | `POST /v2/spaces/{space_id}/workflows/evidence-search/tasks` or `POST /v2/spaces/{space_id}/chat-sessions/{session_id}/messages` | Ask "What is the strongest MED13 evidence?" |
| 7. Find gaps and repeat | Keep the research space fresh over time | `POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups`, `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks`, or `POST /v2/spaces/{space_id}/schedules` | Add "Now focus on neurodevelopmental phenotypes and loss-of-function variants" |

## Manual And Advanced Paths

Most researchers should start with `evidence-runs`. These endpoints are useful
when you need more control or debugging visibility.

| Goal | Endpoint(s) | When to use it |
| --- | --- | --- |
| Inspect sources | `GET /v2/sources` | Confirm which sources support direct search or enrichment |
| Search one source directly | `POST /v2/spaces/{space_id}/sources/{source_key}/searches` | Manually pre-capture or debug source-specific results |
| Hand off one selected source result | `POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs` | Manually turn one captured result into extraction input |
| Create a research plan | `POST /v2/spaces/{space_id}/research-plan` | Use source-enrichment planning workflows |
| Add your own evidence | `POST /v2/spaces/{space_id}/documents/text` and `POST /v2/spaces/{space_id}/documents/pdf` | Upload a MED13 paper, note, or copied abstract |
| Extract from one document | `POST /v2/spaces/{space_id}/documents/{document_id}/extraction` | Turn a specific document into reviewable suggestions |

## The Most Important Rule

The AI can find evidence and create proposals, but the review items list is the gate
between "the system found something" and "this is trusted graph knowledge."

Humans promote or reject proposals before they become official graph state.
