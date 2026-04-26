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
| 1. Choose topic | Create or get a research space | `POST /v2/spaces` or `PUT /v2/spaces/default` | Create "MED13 Workspace" |
| 2. Inspect sources | See which sources support direct search or research-plan enrichment | `GET /v2/sources` | Confirm which MED13 sources can be searched directly |
| 3. Define research plan | Tell the system the research goal and source mix | `POST /v2/spaces/{space_id}/research-plan` | "Understand MED13 and cardiomyopathy using PubMed, MARRVEL, and ClinVar" |
| 4. Add your own evidence | Upload text notes or PDFs | `POST /v2/spaces/{space_id}/documents/text` and `POST /v2/spaces/{space_id}/documents/pdf` | Upload a MED13 paper, note, or copied abstract |
| 5. Search sources directly | Run source-specific discovery for direct-search sources | `POST /v2/spaces/{space_id}/sources/{source_key}/searches` | Search PubMed papers, ClinVar variants, or model-organism sources |
| 6. Extract proposals | Turn documents or evidence into reviewable suggestions | `POST /v2/spaces/{space_id}/documents/{document_id}/extraction` | Extract MED13 claims, entities, observations, or variants |
| 7. Review proposals | Have a human approve, reject, or resolve staged work | `GET /v2/spaces/{space_id}/review-items` and `POST /v2/spaces/{space_id}/review-items/{item_id}/decision` | Promote strong evidence and reject weak claims |
| 8. Build graph | Approved proposals become trusted graph knowledge | Review action with `{"action": "promote"}` | Add an approved MED13 claim to the graph |
| 9. Explore graph | Browse trusted entities, claims, and evidence | `GET /v2/spaces/{space_id}/evidence-map/entities`, `GET /v2/spaces/{space_id}/evidence-map/claims`, and `GET /v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence` | See MED13 claims and supporting evidence |
| 10. Ask questions | Query the graph and documents with AI | `POST /v2/spaces/{space_id}/workflows/evidence-search/tasks` or `POST /v2/spaces/{space_id}/chat-sessions/{session_id}/messages` | Ask "What is the strongest MED13 evidence?" |
| 11. Find gaps and repeat | Keep the research space fresh over time | `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks` or `POST /v2/spaces/{space_id}/schedules` | Re-run discovery when new MED13 evidence appears |

## The Most Important Rule

The AI can find evidence and create proposals, but the review items list is the gate
between "the system found something" and "this is trusted graph knowledge."

Humans promote or reject proposals before they become official graph state.
