# Inbox UI Specification For `research_inbox`, `research_inbox_runtime`, and `artana_evidence_api`

## Purpose

This document defines a Gmail-like, task-oriented inbox UX across:

- `/Users/alvaro1/Documents/med13/foundation/resource_library/services/research_inbox`
- `/Users/alvaro1/Documents/med13/foundation/resource_library/services/research_inbox_runtime`
- `/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_api`

The goal is to make long-running, asynchronous research workflows feel natural
to users who already understand email-like products:

- a research request becomes a thread
- the system works in the background
- follow-up questions appear inline
- approvals and validations appear as action cards
- completed work is archived

This spec is intentionally grounded in the current service split. Where the
desired inbox behavior is not directly supported by the current implementation,
this doc labels it as either:

- `Client-derived`: can be implemented by combining existing endpoints
- `New API needed`: would require new backend support

## Current Architecture Boundary

The current inbox implementation is not harness-only.

### `research_inbox`

- Next.js UI
- sidebar, thread list, thread detail, composer, and local interaction design
- renders a product thread model and local read-model projections

### `research_inbox_runtime`

- canonical inbox runtime
- owns `thread`, `message`, and `command` lifecycle
- owns queueing, idempotency, routing, and async orchestration
- creates initial system messages and stores canonical researcher / AI turns
- does **not** own prompts or LLM execution

### `artana_evidence_api`

- AI semantics and background run execution
- Artana kernel, typed workflows, prompts, and research-state reasoning
- returns structured assistant content and workflow artifacts
- does **not** own inbox rendering or thread UX

## Product Thesis

The system should not feel like a workflow engine or AI ops console.

It should feel like:

- an inbox of research tasks
- threaded conversations with the system
- review requests embedded inside the same thread
- a small number of clear human states:
  - `Waiting on you`
  - `Waiting on system`
  - `Ready to review`
  - `Done`

The deeper design principle is:

> A research request is not a one-shot chat prompt. It is a durable task thread
> with messages, background work, review gates, and a final deliverable.

## Service Grounding Summary

The current product experience is grounded in two backend layers:

- `research_inbox_runtime` for canonical inbox operations
- `artana_evidence_api` for AI workflows, run activity, proposals, approvals, and artifacts

### Primary route groups

| UI concern | Primary routes |
| --- | --- |
| Service health and harness discovery | `artana_evidence_api: GET /health`, `GET /v1/harnesses`, `GET /v1/harnesses/{harness_id}` |
| Canonical inbox threads and messages | `research_inbox_runtime: POST /v1/spaces/{space_id}/onboarding`, `POST /v1/threads/{thread_id}/messages` |
| Generic runs | `artana_evidence_api: POST /v1/spaces/{space_id}/runs`, `GET /v1/spaces/{space_id}/runs`, `GET /v1/spaces/{space_id}/runs/{run_id}` |
| Run activity and transparency | `artana_evidence_api: GET /progress`, `GET /events`, `GET /capabilities`, `GET /policy-decisions`, `GET /workspace`, `GET /artifacts`, `GET /artifacts/{artifact_key}` |
| Pause/resume | `artana_evidence_api: POST /v1/spaces/{space_id}/runs/{run_id}/resume` |
| Chat threads | `artana_evidence_api: GET/POST /v1/spaces/{space_id}/chat-sessions`, `GET /v1/spaces/{space_id}/chat-sessions/{session_id}`, `POST /messages` |
| Proposals | `artana_evidence_api: GET /v1/spaces/{space_id}/proposals`, `GET /v1/spaces/{space_id}/proposals/{proposal_id}`, `POST /promote`, `POST /reject` |
| Approvals | `artana_evidence_api: GET /v1/spaces/{space_id}/runs/{run_id}/approvals`, `POST /approvals/{approval_key}` |
| Schedules | `artana_evidence_api: GET/POST/PATCH /v1/spaces/{space_id}/schedules`, `POST /pause`, `POST /resume`, `POST /run-now` |
| Typed workflows | `artana_evidence_api: POST /agents/graph-search/runs`, `POST /agents/graph-connections/runs`, `POST /agents/hypotheses/runs`, `POST /agents/research-bootstrap/runs`, `POST /agents/continuous-learning/runs`, `POST /agents/mechanism-discovery/runs`, `POST /agents/graph-curation/runs`, `POST /agents/supervisor/runs` |
| Supervisor views | `artana_evidence_api: GET /agents/supervisor/runs`, `GET /agents/supervisor/runs/{run_id}`, `GET /agents/supervisor/dashboard` |

### Important persistent objects in the product

| Object | Meaning in the product |
| --- | --- |
| `runtime thread` | canonical inbox thread |
| `runtime message` | canonical user, system, or AI message |
| `runtime command` | queued deterministic action that advances a thread |
| `run` | one execution of background work |
| `progress` | current user-facing state of a run |
| `event` | raw lifecycle trace |
| `artifact` | a named result or report |
| `workspace` | current structured snapshot of the run state |
| `chat session` | durable thread container for conversational work |
| `proposal` | staged candidate graph update |
| `approval` | gated human decision before risky action |
| `schedule` | recurring background task |
| `capabilities` | what tools the run was allowed to use |
| `policy-decisions` | what the run actually did, plus later manual review |

## UX Model

### Top-level user object: Inbox Thread

The UI should expose a single top-level object:

- `Inbox thread`

An inbox thread is a product-level object backed by:

- one canonical runtime thread
- zero or more runtime messages
- zero or more runtime commands
- one or more runs
- zero or more proposals
- zero or more approvals
- one or more artifacts
- a current state derived from progress, workspace, approvals, and proposals

This means the current implementation is:

- **not** purely client-derived
- **not** purely harness-derived
- a runtime-owned canonical thread with client-derived enrichment from harness objects

### Why thread-first is the right abstraction

The API is run-centric, but the product should be thread-centric because users
care about:

- what they asked
- what the system is doing
- whether they need to act
- what the answer is

Users should never need to reason in terms of:

- `run_id`
- `artifact_key`
- `resume_point`
- `proposal_type`

Those are implementation details.

## Core Screens

## 1. Inbox List

### Goal

Show only actionable or active research threads.

### Layout

- Left sidebar
  - `Inbox`
  - `Pinned`
  - `Needs Review`
  - `Waiting on System`
  - `Snoozed`
  - `Done`
  - `All`
  - optional labels such as project, disease area, space
- Center list
  - thread rows
- Optional right panel
  - evidence preview
  - activity preview
  - review summary

### Thread row content

Each row should show:

- subject/title
- short preview text
- space or project label
- current state badge
- time of last meaningful activity
- count badges:
  - pending reviews
  - pending approvals
  - new reports
- quick actions:
  - pin
  - snooze
  - archive

### Row state mapping

| UI state | Derived from API |
| --- | --- |
| `Waiting on you` | run status `paused`; pending approvals; unresolved proposal review required |
| `Waiting on system` | run status `queued` or `running` |
| `Ready to review` | proposals in `pending_review`; verified chat graph-write candidates; completed run with reviewable outputs |
| `Done` | run status `completed` and no pending approvals/proposals requiring attention |
| `Failed` | run status `failed` |

### API sources for inbox list

Current best source composition:

- runtime thread/message projection from `research_inbox_runtime`
- `GET /v1/spaces/{space_id}/runs`
- `GET /v1/spaces/{space_id}/proposals`
- `GET /v1/spaces/{space_id}/agents/supervisor/runs`
- `GET /v1/spaces/{space_id}/agents/supervisor/dashboard`

### Support status

- unified inbox list: `Client-derived` over canonical runtime threads plus harness enrichment
- pagination for generic runs: limited, current route returns whole list
- pinning: `New API needed` or client-local preference storage
- snoozing: `New API needed` or client-local preference storage
- archive state: `New API needed` or client-local preference storage
- bundling/grouping rules: `Client-derived`

## 2. Thread Detail View

### Goal

Make one research case feel like a single email thread with embedded task cards.

### Layout

- Header
  - subject
  - status badge
  - space label
  - participants:
    - user
    - research agent/system
  - quick actions:
    - reply
    - approve
    - snooze
    - archive
    - pin
- Main timeline
  - ordered messages and cards
- Secondary panel
  - artifacts
  - evidence
  - activity
  - transparency

### Timeline item types

| Timeline item | Backing data |
| --- | --- |
| User message | runtime message with sender `researcher`; optionally chat message for harness-native chat workflows |
| Assistant update | runtime message with sender `ai`; optionally selected run progress/events summarized |
| System status update | runtime message with sender `system`; optionally run progress + selected lifecycle events |
| Review request card | proposals, approvals, or unresolved mapping surfaced from artifacts/workspace |
| Approval result | approval decision response; proposal promote/reject response |
| Final report card | artifacts such as `research_brief`, `graph_search_result`, `curation_summary`, `supervisor_summary`, `delta_report` |

### Thread header state rules

The header should show only one primary status at a time:

- `Waiting on you`
- `Waiting on system`
- `Review ready`
- `Done`
- `Failed`

Priority order for derived status:

1. pending approvals
2. pending reviewable proposals or inline chat graph-write candidates
3. running or queued runs
4. failed runs
5. completed with final artifacts

## 3. Review Request Cards

### Goal

Turn technical governance steps into familiar, actionable cards inside the
thread.

### Card types required by the current API

#### A. Approval Card

Backed by:

- `GET /v1/spaces/{space_id}/runs/{run_id}/approvals`
- `POST /v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}`
- `POST /v1/spaces/{space_id}/runs/{run_id}/resume`

Must show:

- approval title
- risk level
- target type
- current status
- short explanation
- approve / reject action

Should optionally show:

- target id
- source run
- related artifact

#### B. Proposal Review Card

Backed by:

- `GET /v1/spaces/{space_id}/proposals`
- `GET /v1/spaces/{space_id}/proposals/{proposal_id}`
- `POST /promote`
- `POST /reject`

Must show:

- proposal title
- proposal type
- summary
- confidence
- ranking score
- promote / reject action

Should optionally show:

- evidence bundle summary
- related run
- related artifact

#### C. Chat Graph-Write Candidate Card

Backed by:

- `POST /v1/spaces/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review`
- `POST /v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write`

Must show:

- candidate summary
- verification status
- promote / reject / stage-as-proposal actions

This card is especially important because it lets the UI keep the review
experience inside the thread instead of forcing a switch to a proposal queue.

#### D. Entity Or Relation Validation Card

This is a desired UX element, but it is only partially represented in the
current API.

Today it would need to be surfaced from:

- run artifacts
- run workspace snapshot
- proposal payloads
- curation packet / review plan artifacts

Support status:

- renderable when the relevant workflow artifacts include unresolved mapping
  details: `Client-derived`
- dedicated first-class validation endpoints: `New API needed`

## 4. Artifacts Panel

### Goal

Make final outputs and important intermediate reports feel like email
attachments.

### Minimum artifact groups

| Group | Common artifact keys |
| --- | --- |
| Research summary | `research_brief`, `graph_search_result`, `supervisor_summary`, `curation_summary` |
| Graph context | `graph_context_snapshot`, `graph_summary`, `graph_chat_result` |
| Review packages | `candidate_claim_pack`, `review_plan`, `approval_intent`, `graph_write_proposals` |
| Learning reports | `delta_report` |
| Transparency | `run_capabilities`, `policy_decisions` |

### API sources

- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts`
- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts/{artifact_key}`

### UX behavior

- show artifact list as attachment-like pills or cards
- pin final artifacts to top of thread
- collapse low-value technical artifacts by default
- show created or updated time if available

## 5. Activity Panel

### Goal

Keep machine-level activity available without polluting the main thread.

### Sources

- `GET /v1/spaces/{space_id}/runs/{run_id}/progress`
- `GET /v1/spaces/{space_id}/runs/{run_id}/events`
- `GET /v1/spaces/{space_id}/runs/{run_id}/workspace`

### What to show

- current phase
- progress percentage
- latest message
- timeline of major lifecycle steps
- resume point if paused
- pending approvals count if relevant

### What not to show by default

- every low-level event as a main-thread message
- raw JSON payloads
- internal step keys unless the user opens debug details

## 6. Transparency Panel

### Goal

Provide a clean audit and trust view for advanced users, reviewers, and admins.

### Sources

- `GET /v1/spaces/{space_id}/runs/{run_id}/capabilities`
- `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions`

### UX structure

- Tab 1: `Allowed Tools`
  - visible tools
  - filtered tools
  - policy profile
- Tab 2: `Actual Decisions`
  - ordered policy decisions
  - tool decisions
  - manual review decisions

### Why this matters in the inbox UX

This panel preserves trust and auditability without forcing normal users to
read operational traces in the main thread.

## Thread Creation Flows

## 1. Start From Chat

### Best when

- the user wants to ask a question naturally
- the user expects conversational follow-up
- the work may later stage graph-write proposals

### API flow

1. `POST /v1/spaces/{space_id}/chat-sessions`
2. `POST /v1/spaces/{space_id}/chat-sessions/{session_id}/messages`
3. render returned `run`
4. poll `progress`
5. read `artifacts`
6. if needed, review inline graph-write candidates or stage proposals

### Product interpretation

- creates a new inbox thread, ideally mirrored into `research_inbox_runtime`
- first user message is the thread opener
- background run becomes thread activity

## 2. Start From Structured Workflow

### Best when

- the user wants a known research mode such as bootstrap, curation, continuous
  learning, or supervisor

### API flow

Create one typed run:

- graph search
- graph connections
- hypothesis exploration
- research bootstrap
- continuous learning
- mechanism discovery
- claim curation
- supervisor

### Product interpretation

- either create a new runtime thread directly
- or create a runtime thread seeded by a system-authored opener such as:
  - `Started research bootstrap for MED13`

## 3. Start From Schedule

### Best when

- the user wants continuous background monitoring

### API flow

1. `POST /v1/spaces/{space_id}/schedules`
2. optional `POST /run-now`
3. later runs appear in the inbox as fresh thread activity

### Product interpretation

- schedule detail is not itself a thread
- each actual run generated by the schedule can appear as:
  - activity on an existing thread, or
  - a new thread in a “Monitoring” or “Updates” bundle

## Workflow-Specific UX Requirements

## 1. Graph Search

User expectation:

- ask a question
- get an answer with evidence

Required UI:

- single answer card
- evidence summary
- related artifacts

Primary route:

- `POST /v1/spaces/{space_id}/agents/graph-search/runs`

## 2. Research Bootstrap

User expectation:

- initialize a space
- get an initial brief
- stage first proposals

Required UI:

- kickoff thread
- graph snapshot attachment
- research brief attachment
- proposal review queue

Primary route:

- `POST /v1/spaces/{space_id}/agents/research-bootstrap/runs`

## 3. Continuous Learning

User expectation:

- monitor the space over time
- surface only net-new findings

Required UI:

- delta report attachment
- “new evidence found” thread updates
- schedule controls

Primary routes:

- `POST /v1/spaces/{space_id}/agents/continuous-learning/runs`
- schedule routes

## 4. Mechanism Discovery

User expectation:

- discover ranked candidate mechanisms

Required UI:

- candidate list card
- staged mechanism proposals

Primary route:

- `POST /v1/spaces/{space_id}/agents/mechanism-discovery/runs`

## 5. Claim Curation

User expectation:

- review staged proposals
- approve before write

Required UI:

- curation packet attachment
- approval cards
- explicit resume action after approvals

Primary routes:

- `POST /v1/spaces/{space_id}/agents/graph-curation/runs`
- approvals routes
- run resume route

## 6. Supervisor

User expectation:

- one parent thread coordinating bootstrap, chat, and curation

Required UI:

- parent thread summary
- child run references
- approval pause/resume awareness
- dashboard views

Primary routes:

- `POST /v1/spaces/{space_id}/agents/supervisor/runs`
- `GET /v1/spaces/{space_id}/agents/supervisor/runs`
- `GET /v1/spaces/{space_id}/agents/supervisor/runs/{run_id}`
- `GET /v1/spaces/{space_id}/agents/supervisor/dashboard`

## Message And Card Taxonomy

The UI should support these normalized thread items.

| UI item type | Description | Primary source |
| --- | --- | --- |
| `user_message` | user asks question or starts task | runtime message |
| `assistant_message` | conversational answer or update | runtime message |
| `system_status` | queued/running/paused/completed summary | runtime message and/or run progress + events |
| `artifact_ready` | a report or package is available | artifact list |
| `proposal_review` | staged proposal needs action | proposals |
| `approval_review` | gated action requires approval | approvals |
| `resume_required` | all approvals resolved, run can continue | approvals + run progress |
| `final_report` | thread deliverable is ready | artifacts |
| `transparency_update` | optional advanced audit card | policy-decisions |

## Required Derived Fields For The Frontend

The frontend will need a normalization layer that derives product fields from
multiple runtime and harness objects.

### Required thread-level derived fields

- `thread_id`
- `thread_kind`
  - `chat`
  - `workflow`
  - `schedule_update`
  - `supervisor`
- `subject`
- `preview_text`
- `runtime_thread_id`
- `primary_run_id`
- `chat_session_id`
- `latest_activity_at`
- `status`
- `needs_user_action`
- `pending_approval_count`
- `pending_proposal_count`
- `artifact_keys`
- `has_final_report`
- `labels`
- `bundle_key`

### Required message/card-level derived fields

- `thread_item_id`
- `thread_item_type`
- `created_at`
- `title`
- `body`
- `source_run_id`
- `source_artifact_key`
- `action_primary`
- `action_secondary`

## Gmail-Like Behaviors

## 1. Pin

### Purpose

Keep active, important threads at the top.

### Support status

- `New API needed` for server-backed sync across devices
- otherwise `Client-derived` with local preference storage

## 2. Snooze

### Purpose

Hide a thread until:

- a time
- a date
- system completion
- a review-required state

### Support status

- time/date snooze: `New API needed` for durable multi-device behavior
- local-only snooze: `Client-derived`
- “wake on system completion”: `Client-derived` if the client polls run state

## 3. Archive

### Purpose

Remove done threads from the main inbox while keeping them searchable.

### Support status

- `New API needed` for durable shared archive state
- local-only archive: `Client-derived`

## 4. Bundles

### Purpose

Group lower-signal or recurring updates.

Suggested bundles:

- `Monitoring`
- `Literature Refresh`
- `Completed Reports`
- `Supervisor Updates`

### Support status

- `Client-derived`

## Search And Filtering

The inbox should support at least:

- by status
- by harness/workflow type
- by proposal state
- by pending approvals
- by created/updated time
- by supervisor-specific filters
- by space

### Current API support

| Need | Current support |
| --- | --- |
| filter proposals by `status`, `proposal_type`, `run_id` | supported |
| filter supervisor runs by `status`, `curation_source`, `has_chat_graph_write_reviews`, time window, pagination, sorting | supported |
| generic runs filtering | not first-class |
| chat session filtering | not first-class |

## Notifications

The inbox should generate notifications when:

- a run moves to `paused`
- a new approval appears
- a new proposal enters `pending_review`
- a final report artifact is created
- a supervisor parent run completes

### Support status

- polling-based notification generation: `Client-derived`
- push/webhook delivery: `New API needed`

## MED13 Example Thread

This is the canonical example for the desired UX.

### Subject

`Investigate MED13 and congenital heart disease`

### Thread timeline

1. User message
   - “Find the strongest evidence linking MED13 to congenital heart disease.”
2. System status
   - “Started literature and graph search.”
3. System status
   - “Found 8 relevant papers and 2 candidate graph links.”
4. Review request card
   - “Validate disease mapping for ‘congenital heart disease’.”
5. User action
   - approve preferred disease mapping
6. System status
   - “Research resumed.”
7. Proposal review card
   - “Review candidate claim: MED13 associated with congenital heart disease.”
8. User action
   - promote proposal
9. Final report card
   - evidence summary
   - graph update status
   - links to `research_brief` or `curation_summary`

### Likely API calls behind this thread

- create chat session or bootstrap run
- create run
- poll run progress
- inspect artifacts
- list proposals
- promote proposal
- inspect policy decisions

## Minimum Viable Product

The MVP inbox should include only features that are already well-supported by
the current API.

### MVP scope

- inbox list aggregated client-side
- thread detail for chat sessions and runs
- status badges from run progress
- artifact list and final report cards
- proposal review cards
- approval review cards
- resume action
- transparency panel
- supervisor list and detail integration

### Out of MVP

- server-backed pin
- server-backed snooze
- server-backed archive
- first-class validation queue endpoints
- websocket or push notifications
- first-class global “thread” resource

## Recommended Backend Additions

To fully realize the Gmail-like inbox model, the following backend additions
would materially simplify the UI.

### 1. Unified thread resource

Examples:

- `GET /v1/spaces/{space_id}/threads`
- `GET /v1/spaces/{space_id}/threads/{thread_id}`

This would let the backend define the canonical aggregation over chat sessions,
runs, proposals, approvals, and artifacts.

### 2. Durable inbox preferences

Examples:

- pin
- snooze until timestamp
- archive/unarchive
- labels
- bundle assignment

### 3. First-class validation review endpoints

Examples:

- unknown entity mapping review
- unknown relation mapping review
- synonym confirmation

### 4. Notification delivery

Examples:

- webhook
- websocket
- server-sent events

## Implementation Guidance For Frontend Teams

### Normalize first

Do not bind UI components directly to raw route responses.

Build a client-side normalization layer that:

- combines runs, chat sessions, proposals, approvals, and artifacts
- derives inbox-friendly statuses
- emits stable thread items for rendering

### Prefer meaningful summaries over raw events

Use:

- progress
- approvals
- proposals
- artifacts

before falling back to:

- raw events

### Keep technical detail available but secondary

Use the main thread for:

- meaningful updates
- review actions
- final results

Use side panels or expandable sections for:

- transparency
- raw activity
- debug details

## Acceptance Criteria

An inbox UI built to this spec should let a user:

- start a research request naturally
- leave and come back later
- understand whether the system or the human is blocked
- review proposals and approvals in the same thread
- inspect final reports as attachments
- audit what the run could do and what it actually did
- archive completed work without losing history

If the product achieves those outcomes, the harness container will feel like a
natural inbox-driven research system rather than a specialized orchestration
tool.
