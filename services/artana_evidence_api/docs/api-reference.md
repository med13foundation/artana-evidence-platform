# API Reference

Base URL examples in this file assume:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export ARTANA_API_KEY="art_sk_your_key"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
```

Normal auth can use either:

```bash
-H "Authorization: Bearer $TOKEN"
```

or:

```bash
-H "X-Artana-Key: $ARTANA_API_KEY"
```

For self-hosted bootstrap, the first-user route uses:

```bash
-H "X-Artana-Bootstrap-Key: $ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"
```

## Endpoint Families

The current endpoint surface is easiest to understand in layers:

1. auth and space setup
2. generic run lifecycle and transparency
3. document, review, and chat workflows
4. direct discovery and evidence-map reads
5. typed research workflows

One important runtime rule:

- many run-start routes are queue-first
- they may return `201 Created` with a completed result
- or `202 Accepted` when the caller sends `Prefer: respond-async` or the sync
  wait budget expires

## V2 Public Naming

`/v2` is the user-facing naming layer. It keeps the same underlying workflow
behavior, but uses product terms instead of runtime terms:

| V1 term | V2 term | Why |
| --- | --- | --- |
| `runs` | `tasks` | A task is one piece of work the user asked Artana to do. |
| `agents/*/runs` | `workflows/*/tasks` | Users choose workflows; the backend decides how to execute them. |
| `review-queue` | `review-items` | The resource is the set of items needing human review. |
| `graph-explorer` | `evidence-map` | The product surface is evidence-first, not graph-internal. |
| `graph-write-candidates` | `suggested-updates` | Chat produces suggested evidence-map updates. |
| `artifacts` | `outputs` | Users inspect outputs from a task. |
| `policy-decisions` | `decisions` | Users and auditors inspect what the task decided to do. |

Recommended v2 entry points:

| Goal | Path |
| --- | --- |
| Start or list tasks | `/v2/spaces/{space_id}/tasks` |
| Inspect a task | `/v2/spaces/{space_id}/tasks/{task_id}` |
| Read task progress/events | `/v2/spaces/{space_id}/tasks/{task_id}/progress` and `/events` |
| Read task outputs | `/v2/spaces/{space_id}/tasks/{task_id}/outputs` |
| Review pending items | `/v2/spaces/{space_id}/review-items` |
| Start topic setup | `/v2/spaces/{space_id}/workflows/topic-setup/tasks` |
| Start evidence curation | `/v2/spaces/{space_id}/workflows/evidence-curation/tasks` |
| Start full research | `/v2/spaces/{space_id}/workflows/full-research/tasks` |
| Browse trusted evidence | `/v2/spaces/{space_id}/evidence-map/*` |
| Stage chat-suggested updates | `/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates` |

The sections below are v2-first and use the public task/workflow naming.

## 1. Health And Authentication

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | Returns service health. |
| `POST` | `/v2/auth/bootstrap` | Creates the first self-hosted user and initial API key. |
| `GET` | `/v2/auth/me` | Returns the current authenticated identity plus default space when present. |
| `GET` | `/v2/auth/api-keys` | Lists API keys for the authenticated user. |
| `POST` | `/v2/auth/api-keys` | Creates an additional API key for the authenticated user. |
| `DELETE` | `/v2/auth/api-keys/{key_id}` | Revokes one API key. |
| `POST` | `/v2/auth/api-keys/{key_id}/rotate` | Rotates one API key and returns the new secret once. |

Bootstrap request body:

```json
{
  "email": "developer@example.com",
  "username": "developer",
  "full_name": "Developer Example",
  "role": "researcher",
  "api_key_name": "Default SDK Key",
  "api_key_description": "Local development key",
  "create_default_space": true
}
```

Create extra API key body:

```json
{
  "name": "CLI Key",
  "description": "Used by local scripts"
}
```

Useful first check:

```bash
curl -s "$HARNESS_URL/v2/auth/me" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

## 2. Spaces, Membership, Settings, And Research State

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces` | Lists spaces visible to the caller. |
| `POST` | `/v2/spaces` | Creates a space. |
| `PUT` | `/v2/spaces/default` | Gets or creates the caller's personal default space. |
| `DELETE` | `/v2/spaces/{space_id}` | Archives a space. |
| `GET` | `/v2/spaces/{space_id}/members` | Lists space members. |
| `POST` | `/v2/spaces/{space_id}/members` | Adds one member to the space. |
| `DELETE` | `/v2/spaces/{space_id}/members/{user_id}` | Removes one member from the space. |
| `PATCH` | `/v2/spaces/{space_id}/settings` | Updates owner-managed space settings. |
| `GET` | `/v2/spaces/{space_id}/research-state` | Returns the current long-lived research state snapshot. |

Create space body:

```json
{
  "name": "MED13 Workspace",
  "description": "Governed evidence review for MED13",
  "sources": {
    "pubmed": true,
    "marrvel": true,
    "clinvar": true,
    "mondo": true,
    "pdf": true,
    "text": true,
    "drugbank": false,
    "alphafold": false,
    "uniprot": false,
    "hgnc": false,
    "clinical_trials": false,
    "mgi": false,
    "zfin": false
  }
}
```

Settings update body:

```json
{
  "research_orchestration_mode": "full_ai_guarded",
  "full_ai_guarded_rollout_profile": "guarded_low_risk"
}
```

Use `PUT /v2/spaces/default` when you just want one working space without
choosing a slug or creating space metadata manually.

## 3. Workflow Templates

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/workflow-templates` | Lists available workflow templates. |
| `GET` | `/v2/workflow-templates/{template_id}` | Returns one workflow template. |

## 4. Generic Task Lifecycle And Transparency

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/tasks` | Starts one generic task by `workflow_template_id`. |
| `GET` | `/v2/spaces/{space_id}/tasks` | Lists tasks in a space. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}` | Returns one task. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/progress` | Returns the latest progress snapshot. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/events` | Returns lifecycle events. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/capabilities` | Returns the frozen tool and policy snapshot for the task. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/decisions` | Returns ordered tool and review decisions for the task. |
| `POST` | `/v2/spaces/{space_id}/tasks/{task_id}/resume` | Resumes a paused task. |

Generic run creation body:

```json
{
  "workflow_template_id": "research-bootstrap",
  "title": "Bootstrap MED13 evidence map",
  "input_payload": {
    "objective": "Find the strongest evidence for MED13 in congenital heart disease",
    "source_type": "pubmed",
    "max_depth": 2
  }
}
```

Transparency endpoints answer:

- what tools the task could use
- what tools it actually used
- whether later manual review changed the final story

## 5. Outputs, Working State, Plans, And Approvals

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/outputs` | Lists output keys for one task. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}` | Returns one output. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/working-state` | Returns the latest working-state snapshot. |
| `POST` | `/v2/spaces/{space_id}/tasks/{task_id}/planned-actions` | Records a task plan with proposed actions. |
| `GET` | `/v2/spaces/{space_id}/tasks/{task_id}/approvals` | Lists approvals for a task. |
| `POST` | `/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}` | Approves or rejects one gated action. |

Intent request body:

```json
{
  "summary": "Review the proposed graph mutations before applying them.",
  "proposed_actions": [
    {
      "approval_key": "claim-1",
      "title": "Promote candidate claim",
      "risk_level": "medium",
      "target_type": "claim",
      "target_id": "candidate-claim-1",
      "requires_approval": true,
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

Approval request body:

```json
{
  "decision": "approved",
  "reason": "Evidence is sufficient"
}
```

## 6. Chat Sessions

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/chat-sessions` | Lists chat sessions. |
| `POST` | `/v2/spaces/{space_id}/chat-sessions` | Creates a chat session. |
| `GET` | `/v2/spaces/{space_id}/chat-sessions/{session_id}` | Returns one session with message history. |
| `POST` | `/v2/spaces/{space_id}/chat-sessions/{session_id}/messages` | Sends one chat message and runs grounded chat. |
| `GET` | `/v2/spaces/{space_id}/chat-sessions/{session_id}/messages/{task_id}/stream` | Streams chat run events for the given message run. |
| `POST` | `/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates` | Converts reviewed chat findings into staged graph proposals. |
| `POST` | `/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates/{candidate_index}/decision` | Promotes or rejects one inline chat candidate. |

Create session body:

```json
{
  "title": "MED13 briefing"
}
```

Send message body:

```json
{
  "content": "What is the strongest evidence linking MED13 to congenital heart disease?",
  "model_id": "gpt-5",
  "max_depth": 2,
  "top_k": 10,
  "include_evidence_chains": true,
  "document_ids": [
    "77777777-7777-7777-7777-777777777777"
  ],
  "refresh_pubmed_if_needed": true
}
```

The default governed path is:

1. send the chat message
2. stage generic proposals with `/suggested-updates`
3. review those items through `/review-items`

Inline chat-candidate review still exists, but it is the advanced path.

## 7. Documents And Extraction

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/documents` | Lists tracked documents. |
| `GET` | `/v2/spaces/{space_id}/documents/{document_id}` | Returns one tracked document. |
| `POST` | `/v2/spaces/{space_id}/documents/text` | Submits raw text as a tracked document. |
| `POST` | `/v2/spaces/{space_id}/documents/pdf` | Uploads a PDF and stores the raw binary for later enrichment. |
| `POST` | `/v2/spaces/{space_id}/documents/{document_id}/extraction` | Runs extraction and returns staged proposals, review-only items, and skipped diagnostics. |

Text submission body:

```json
{
  "title": "MED13 evidence note",
  "text": "MED13 associates with cardiomyopathy.",
  "metadata": {
    "origin": "notes"
  }
}
```

PDF upload uses multipart form data with:

- `file`
- optional `title`
- optional `metadata_json`

Important extract behavior:

- PDFs are enriched during extract time, not upload time
- genomics-capable documents use the variant-aware extraction path
- retries can reuse matching already-staged proposals and review items instead
  of returning an empty result

Variant-aware extraction can stage:

- `entity_candidate` proposals for anchored variants
- `observation_candidate` proposals for transcript, HGVS fields,
  classification, zygosity, inheritance, exon, or coordinates
- `candidate_claim` proposals for phenotype and mechanism claims
- explicit review items when extraction stays incomplete

Important promotion nuance:

- promoting an `observation_candidate` expects the subject entity to already
  exist in the graph
- promote the linked entity candidate first if the subject is still new

## 8. Review Queue And Proposals

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/review-items` | Lists the unified review queue across proposals, review-only items, and approvals. |
| `GET` | `/v2/spaces/{space_id}/review-items/{item_id}` | Returns one review queue item. |
| `POST` | `/v2/spaces/{space_id}/review-items/{item_id}/decision` | Applies one review action through the unified queue surface. |
| `GET` | `/v2/spaces/{space_id}/proposed-updates` | Lists proposal records directly. |
| `GET` | `/v2/spaces/{space_id}/proposed-updates/{proposal_id}` | Returns one proposal. |
| `POST` | `/v2/spaces/{space_id}/proposed-updates/{proposal_id}/promote` | Promotes one proposal directly. |
| `POST` | `/v2/spaces/{space_id}/proposed-updates/{proposal_id}/reject` | Rejects one proposal directly. |

Use `/review-items` as the default human review API.

Useful review-items filters:

- `status`
- `item_type`
- `kind`
- `task_id`
- `document_id`
- `source_family`

Common review-item actions:

- proposals: `promote`, `reject`
- review-only items: `convert_to_proposal`, `mark_resolved`, `dismiss`
- approvals: `approve`, `reject`

Compatibility note:

- `resolve` is still accepted as an alias for `mark_resolved`
- new clients should send `mark_resolved`

Action body:

```json
{
  "action": "promote",
  "reason": "Reviewed and approved",
  "metadata": {}
}
```

Proposal list filters:

- `status`
- `proposal_type`
- `task_id`
- `document_id`

Think of `/proposed-updates` as the lower-level primitive behind the unified
review queue.

## 9. Evidence Map

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/evidence-map/entities` | Lists graph entities with optional search or type filters. |
| `GET` | `/v2/spaces/{space_id}/evidence-map/entities/{entity_id}/claims` | Lists claims linked to one entity. |
| `GET` | `/v2/spaces/{space_id}/evidence-map/claims` | Lists graph claims. |
| `GET` | `/v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence` | Lists evidence rows for one claim. |
| `POST` | `/v2/spaces/{space_id}/evidence-map/document` | Returns a unified graph document with claim and evidence overlays. |

Entity list query parameters:

- `q`
- `entity_type`
- `ids`
- `offset`
- `limit`

Claim list query parameters:

- `claim_status`
- `offset`
- `limit`

Unified graph document request body:

```json
{
  "mode": "seeded",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "include_claims": true,
  "include_evidence": true
}
```

Use the evidence map when you want read-only graph inspection without starting a
new AI run.

## 10. Direct Source Discovery

### PubMed

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/sources/pubmed/searches` | Runs one saved PubMed search. |
| `GET` | `/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}` | Returns one saved PubMed job. |

PubMed search body:

```json
{
  "parameters": {
    "gene_symbol": "MED13",
    "search_term": "MED13 cardiomyopathy",
    "date_from": null,
    "date_to": null,
    "publication_types": [],
    "languages": [],
    "sort_by": "relevance",
    "max_results": 25,
    "additional_terms": null
  }
}
```

### MARRVEL

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/sources/marrvel/searches` | Runs one MARRVEL discovery search. |
| `GET` | `/v2/spaces/{space_id}/sources/marrvel/searches/{result_id}` | Returns one saved MARRVEL result. |
| `POST` | `/v2/spaces/{space_id}/sources/marrvel/ingestion` | Fetches MARRVEL gene data and seeds graph entities directly. |

MARRVEL search body:

```json
{
  "gene_symbol": "MED13",
  "taxon_id": 9606,
  "panels": [
    "omim",
    "clinvar",
    "gnomad"
  ]
}
```

MARRVEL also supports `variant_hgvs` or `protein_variant` instead of
`gene_symbol`.

MARRVEL ingest body:

```json
{
  "gene_symbols": [
    "MED13"
  ],
  "taxon_id": 9606
}
```

`/sources/marrvel/ingestion` is the advanced direct-write path. Normal researcher workflows
should prefer search plus governed follow-up review.

## 11. Research Init And Onboarding

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/research-plan` | Initializes a space from natural language and selected sources. |
| `POST` | `/v2/spaces/{space_id}/workflows/research-onboarding/tasks` | Creates the first onboarding assistant message for a space. |
| `POST` | `/v2/spaces/{space_id}/workflows/research-onboarding/turns` | Continues one onboarding thread after a researcher reply. |

Research-init body:

```json
{
  "objective": "Understand MED13 mechanisms and translational evidence",
  "seed_terms": [
    "MED13",
    "cardiomyopathy"
  ],
  "sources": {
    "pubmed": true,
    "marrvel": true,
    "clinvar": true,
    "mondo": true,
    "pdf": true,
    "text": true,
    "drugbank": false,
    "alphafold": false,
    "uniprot": false,
    "hgnc": false,
    "clinical_trials": false,
    "mgi": false,
    "zfin": false
  },
  "max_depth": 2,
  "max_hypotheses": 20,
  "guarded_rollout_profile": "guarded_low_risk"
}
```

Research onboarding start body:

```json
{
  "research_title": "MED13 Translational Mapping",
  "primary_objective": "Understand variant, phenotype, and mechanism evidence around MED13",
  "space_description": "Rare disease research workspace"
}
```

Research onboarding continuation body:

```json
{
  "thread_id": "thread-1",
  "message_id": "message-1",
  "intent": "answer_question",
  "mode": "guided",
  "reply_text": "Start with MED13 variants and phenotype evidence",
  "reply_html": "",
  "attachments": [],
  "contextual_anchor": null
}
```

Use onboarding when you want the service to guide setup conversationally.
Use `research-plan` when you already know the research objective and source mix.

## 12. Analysis And Research Workflow Runs

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/workflows/evidence-search/tasks` | Starts one graph-search run. |
| `POST` | `/v2/spaces/{space_id}/workflows/connection-discovery/tasks` | Starts one graph-connection run. |
| `POST` | `/v2/spaces/{space_id}/workflows/hypothesis-discovery/tasks` | Starts one hypothesis exploration run. |
| `POST` | `/v2/spaces/{space_id}/workflows/topic-setup/tasks` | Starts one research bootstrap run. |
| `POST` | `/v2/spaces/{space_id}/workflows/continuous-review/tasks` | Starts one continuous-learning cycle. |
| `POST` | `/v2/spaces/{space_id}/workflows/mechanism-discovery/tasks` | Starts one mechanism-discovery run. |
| `POST` | `/v2/spaces/{space_id}/workflows/evidence-curation/tasks` | Starts one governed claim-curation run. |
| `POST` | `/v2/spaces/{space_id}/workflows/autopilot/tasks` | Starts one deterministic full AI orchestrator run. |

Graph search body:

```json
{
  "question": "Summarize the strongest MED13 evidence",
  "title": "MED13 graph search",
  "model_id": "gpt-5",
  "max_depth": 2,
  "top_k": 25,
  "curation_statuses": [
    "reviewed"
  ],
  "include_evidence_chains": true
}
```

Research bootstrap body:

```json
{
  "objective": "Map the strongest evidence around MED13 and congenital heart disease",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Research Bootstrap Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_hypotheses": 20,
  "model_id": "gpt-5"
}
```

Continuous-learning body:

```json
{
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Continuous Learning Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_new_proposals": 20,
  "max_next_questions": 5,
  "model_id": "gpt-5",
  "schedule_id": null,
  "run_budget": {
    "max_tool_calls": 20,
    "max_external_queries": 10,
    "max_new_proposals": 20,
    "max_runtime_seconds": 300,
    "max_cost_usd": 5.0
  }
}
```

Graph-curation body:

```json
{
  "proposal_ids": [
    "33333333-3333-3333-3333-333333333333"
  ],
  "title": "Claim Curation Harness"
}
```

Full AI orchestrator body:

```json
{
  "objective": "Understand MED13 mechanisms and translational evidence",
  "seed_terms": [
    "MED13",
    "cardiomyopathy"
  ],
  "title": "Full AI Orchestrator Harness",
  "sources": {
    "pubmed": true,
    "marrvel": true,
    "clinvar": true
  },
  "max_depth": 2,
  "max_hypotheses": 20,
  "planner_mode": "guarded",
  "guarded_rollout_profile": "guarded_low_risk"
}
```

Use `Prefer: respond-async` on these routes when you want a run record returned
immediately instead of waiting for the inline completion window.

## 13. Schedules

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v2/spaces/{space_id}/schedules` | Lists saved schedules. |
| `POST` | `/v2/spaces/{space_id}/schedules` | Creates one schedule. |
| `GET` | `/v2/spaces/{space_id}/schedules/{schedule_id}` | Returns one schedule plus recent tasks. |
| `PATCH` | `/v2/spaces/{space_id}/schedules/{schedule_id}` | Updates one schedule. |
| `POST` | `/v2/spaces/{space_id}/schedules/{schedule_id}/pause` | Pauses one schedule. |
| `POST` | `/v2/spaces/{space_id}/schedules/{schedule_id}/resume` | Resumes one schedule. |
| `POST` | `/v2/spaces/{space_id}/schedules/{schedule_id}/start-now` | Triggers an immediate task from the stored schedule. |

Create schedule body:

```json
{
  "title": "Daily MED13 learning",
  "cadence": "daily",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_new_proposals": 20,
  "max_next_questions": 5,
  "model_id": "gpt-5",
  "run_budget": {
    "max_tool_calls": 20,
    "max_external_queries": 10,
    "max_new_proposals": 20,
    "max_runtime_seconds": 300,
    "max_cost_usd": 5.0
  },
  "metadata": {}
}
```

## 14. Supervisor

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v2/spaces/{space_id}/workflows/full-research/tasks` | Starts one composed supervisor workflow. |
| `GET` | `/v2/spaces/{space_id}/workflows/full-research/tasks` | Lists typed supervisor tasks. |
| `GET` | `/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}` | Returns typed supervisor detail. |
| `GET` | `/v2/spaces/{space_id}/workflows/full-research/dashboard` | Returns typed dashboard summary. |
| `POST` | `/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}/suggested-updates/{candidate_index}/decision` | Promotes or rejects one supervisor briefing-chat candidate. |

Supervisor create body:

```json
{
  "objective": "Map the strongest evidence around MED13 and congenital heart disease",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Supervisor Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_hypotheses": 20,
  "model_id": "gpt-5",
  "include_chat": true,
  "include_curation": true,
  "curation_source": "bootstrap",
  "briefing_question": "What is the strongest evidence I should review first?",
  "chat_max_depth": 2,
  "chat_top_k": 10,
  "chat_include_evidence_chains": true,
  "curation_proposal_limit": 5
}
```

Supervisor list filters:

- `status`
- `curation_source`
- `has_chat_graph_write_reviews`
- `created_after`
- `created_before`
- `updated_after`
- `updated_before`
- `offset`
- `limit`
- `sort_by`
- `sort_direction`

## 15. Primary Versus Advanced Surfaces

Most users should start with:

- `/v2/spaces/default`
- `/v2/spaces/{space_id}/documents/*`
- `/v2/spaces/{space_id}/review-items`
- `/v2/spaces/{space_id}/chat-sessions/*`
- `/v2/spaces/{space_id}/sources/pubmed/searches`
- `/v2/spaces/{space_id}/research-plan`

Advanced or lower-level surfaces:

- `/v2/spaces/{space_id}/proposed-updates/*`
- inline chat candidate review
- `/v2/spaces/{space_id}/sources/marrvel/ingestion`
- evidence-map entity, claim, evidence, and unified-document routes
- `/v2/spaces/{space_id}/members/*`
- `/v2/spaces/{space_id}/settings`
- direct generic `/tasks` creation

## Read Versus Write Access

Read endpoints include:

- health
- auth identity
- harness discovery
- space list
- run list/detail/progress/events/outputs/working-state
- chat session list/detail
- document list/detail
- review queue list/detail
- proposal list/detail
- evidence-map reads
- saved PubMed and MARRVEL result reads
- research state
- supervisor list/detail/dashboard

Write endpoints include:

- bootstrap and API key creation
- space create, settings update, membership updates, and archive
- all run-start routes
- chat message send
- chat graph-write staging
- review queue actions
- proposal promote or reject
- approvals decisions
- document upload, text submit, and extract
- PubMed and MARRVEL search creation
- MARRVEL ingest
- schedule create, update, pause, resume, and run-now
- run resume

Write access generally requires `researcher`, `curator`, or `admin`, while some
space-management routes require space owner or admin authority.
