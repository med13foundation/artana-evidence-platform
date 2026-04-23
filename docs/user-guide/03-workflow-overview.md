# Workflow Overview

The platform is easiest to understand as a loop.

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

## Endpoint Map

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

## The Most Important Rule

The AI can find evidence and create proposals, but the review queue is the gate
between "the system found something" and "this is trusted graph knowledge."

Humans promote or reject proposals before they become official graph state.
