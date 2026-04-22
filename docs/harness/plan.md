# Harness Implementation Plan

## Goal

Build a new standalone service, `services/artana_evidence_api`, that turns a
research space into a durable AI research workspace.

## Implementation Status

As of 2026-03-14, the service surface described below exists and the runtime
path is aligned with this plan: the harness service uses an Artana-backed
runtime for run lifecycle, artifacts, workspace state, progress, events,
resume points, and worker leases; the runnable harness workflows execute
through Artana harness wrappers; manual workflow routes queue kernel-backed
runs and wait on worker-owned execution; and the checked-in harness OpenAPI
contract plus repo-wide `make type-check` and `make test` gates are green.

The service will:

- bootstrap a research space from PubMed and other sources
- store durable research memory outside the graph as artifacts and workspace
  state
- let users open chat sessions against that memory
- run recurring research schedules for continuous learning
- propose or apply governed graph updates through `services/artana_evidence_db`

The design uses Artana as the durable execution and harness runtime, while
`services/artana_evidence_db` remains the graph system of record.

The old mixed runtime design has been removed: the obsolete SQLAlchemy
lifecycle tables for artifacts, workspaces, progress, and events were dropped
after the Artana cutover, while `harness_runs` remains as the persistent run
catalog and SQLAlchemy keeps only non-kernel domain state.

## Scope

### In scope

- new `services/artana_evidence_api` FastAPI service
- Artana kernel, harness, artifact, workspace, and approval integration
- typed tool adapters over graph endpoints and external research endpoints
- research bootstrap, chat, continuous learning, and curation workflows
- recurring schedule definitions and worker execution
- run, artifact, approval, chat, and schedule APIs

### Out of scope

- moving graph persistence out of `services/artana_evidence_db`
- adding fallback or migration paths for older harness designs
- building the full UI in this document
- replacing all existing research flows on day one

## Architecture

### High-level split

```text
Admin UI / Research UI
        |
        v
services/artana_evidence_api
        |
        |-- Artana kernel + harness runtime
        |-- OpenAI / model runtime
        |-- tool registry
        |-- schedules + workers
        |-- artifacts + workspace state
        |-- proposal store
        |-- research state
        |-- run budgets + ranking
        |
        +----> services/artana_evidence_db
        |         |
        |         +-- graph system of record
        |         +-- deterministic graph read/write APIs
        |         +-- claims, evidence, relations, views, reasoning
        |
        +----> PubMed / external source APIs
        |
        +----> extraction / enrichment tools
```

### Responsibility split

`services/artana_evidence_db` owns:

- entities, claims, evidence, provenance, canonical relations
- dictionary governance and graph mutation validation
- graph views, graph documents, reasoning paths, and deterministic query primitives
- graph control-plane and graph repair operations
- no Artana runtime, no OpenAI client, and no model-selection logic

`services/artana_evidence_api` owns:

- Artana run lifecycle
- OpenAI / model-provider access
- harness templates
- chat sessions
- recurring schedules
- research-space memory outside the graph
- proposal store for noisy pre-graph candidates
- structured research state
- run budgets and ranking logic
- approvals and policy-gated writes
- tool orchestration across graph and external sources
- all AI-backed graph search, graph-connection discovery, and hypothesis-generation orchestration

### Deterministic boundary

The target split is strict:

- `services/artana_evidence_db` is deterministic infrastructure that can be controlled by an AI layer, but does not host that AI layer.
- `services/artana_evidence_api` is the only service that should import Artana, instantiate model ports, call OpenAI-compatible providers, or make autonomous run-time decisions.
- all AI-originated graph changes must flow into `services/artana_evidence_db` through typed HTTP endpoints and governed write paths.

## How Artana Is Used

Artana is the runtime substrate, not the graph database.

### Kernel

Use the Artana `Kernel` for:

- replay-safe model and tool execution
- durable run state
- leases for worker execution
- status, progress, resume, and event streaming
- checkpoints and artifacts

Relevant Artana concepts from `docs/artana-kernel/docs`:

- `get_run_status`
- `get_run_progress`
- `resume_point`
- `stream_run_progress`
- `set_artifact` / `get_artifact`
- `set_workspace_state`
- `acquire_run_lease` / `release_run_lease`

### Harness

Use Artana harnesses for structured long-running workflows.

Recommended base:

- `StrongModelAgentHarness` for most user-facing flows
- `SupervisorHarness` only when multiple harnesses must be composed
- `KernelPolicy.enforced_v2()` for governed mutation tools

### Why this fits

This gives the project:

- durable research runs
- resumable chat and schedule cycles
- approval pause and resume
- artifact-backed memory
- deterministic constraints around autonomous model behavior

## Proposed Service Structure

```text
services/artana_evidence_api/
├── app.py
├── main.py
├── config.py
├── auth.py
├── composition.py
├── dependencies.py
├── graph_client.py
├── tool_registry.py
├── harness_registry.py
├── harness_runtime.py
├── research_state.py
├── proposal_store.py
├── graph_snapshot.py
├── run_budget.py
├── ranking.py
├── policy.py
├── scheduler.py
├── worker.py
├── chat_sessions.py
├── supervisor_runtime.py
├── routers/
│   ├── health.py
│   ├── harnesses.py
│   ├── runs.py
│   ├── approvals.py
│   ├── artifacts.py
│   ├── chat.py
│   ├── proposals.py
│   ├── schedules.py
│   ├── research_bootstrap_runs.py
│   ├── continuous_learning_runs.py
│   ├── mechanism_discovery_runs.py
│   ├── graph_curation_runs.py
│   └── supervisor_runs.py
└── openapi.json
```

## Harness Templates

### 1. `ResearchBootstrapHarness`

Purpose:

- create the initial knowledge base for a research space

Typical tools:

- query generation
- PubMed search
- source discovery
- enrichment
- extraction
- graph-write proposal

Outputs:

- research brief artifact
- source inventory artifact
- candidate claim pack
- graph write proposals

### 2. `GraphChatHarness`

Purpose:

- answer user questions inside a research space

Typical tools:

- deterministic graph query tools
- graph document
- graph views
- artifact reads
- optional fresh PubMed retrieval

Outputs:

- grounded answer
- evidence bundle
- chat summary artifact
- optional proposed graph updates

### 3. `ContinuousLearningHarness`

Purpose:

- run scheduled research refresh cycles

Typical tools:

- graph reads
- artifact reads
- literature refresh
- comparison against existing claims
- graph-write proposal

Outputs:

- delta report
- new paper list
- candidate claims
- next-question backlog

### 4. `MechanismDiscoveryHarness`

Purpose:

- detect converging mechanisms from graph structure and reasoning paths

Typical tools:

- reasoning path reads
- graph connections discovery
- claim evidence lookup
- phenotype similarity search
- ranking engine
- graph-write proposal

Outputs:

- mechanism candidates
- mechanism score report
- candidate hypothesis pack

### 5. `ClaimCurationHarness`

Purpose:

- review and apply governed claim updates

Typical tools:

- claims list
- claim evidence
- claim participants
- claim patch
- claim relation create

Outputs:

- curation packet
- curation summary artifact
- approved or rejected actions

## Tool Architecture

The service must separate intelligence from deterministic execution.

### Intelligence side

- harnesses
- prompts
- skill packs
- planning and decision-making

### Deterministic side

- graph HTTP clients
- PubMed and external source clients
- extraction and enrichment adapters
- governed mutation tools

### Tool contract requirements

Each tool should define:

- name
- purpose
- input schema
- output schema
- risk level
- side-effect flag
- capability requirement
- approval requirement
- semantic idempotency policy where applicable

## Research State Model

Artifacts alone are not enough. The service should maintain a structured
research state model per research space.

Suggested fields:

- `objective`
- `current_hypotheses`
- `explored_questions`
- `pending_questions`
- `last_graph_snapshot_id`
- `last_learning_cycle_at`
- `active_schedules`
- `confidence_model`
- `budget_policy`

Purpose:

- prevent repeated searches
- prevent duplicate proposal loops
- give the harness an explicit model of what is already known, explored, or
  still pending

## Graph Snapshot Strategy

Runs should not depend only on the live graph.

Recommended v1 approach:

- add a run-scoped `graph_context_snapshot`
- store it in `artana_evidence_api` and as an Artana artifact
- capture:
  `snapshot_id`, `space_id`, `created_at`, `source_run_id`, relevant claim ids,
  relevant relation ids, graph document hash, and key graph summary fields

This gives reproducibility for a run without requiring a full graph-wide
versioning subsystem on day one.

Future upgrade path:

- if the graph service later exposes first-class graph versioning, evolve this
  into a true `graph_snapshot` read model

## Proposal Store

Do not put early noisy proposals directly into the graph ledger.

Add a service-local proposal store such as:

- `candidate_claims`
- `candidate_hypotheses`
- `mechanism_candidates`

Suggested fields for `candidate_claims`:

- `id`
- `space_id`
- `run_id`
- `source_kind`
- `confidence`
- `reasoning_path`
- `evidence_bundle`
- `status`
- `proposed_claim_type`
- `proposed_subject`
- `proposed_object`

Promotion path:

```text
candidate_claim
-> review
-> relation_claim
-> canonical projection if materializable
```

This keeps the graph cleaner and lets the harness generate aggressively without
polluting the authoritative ledger.

## Budgets And Guardrails

Every run should have explicit budget limits.

Suggested `run_budget` fields:

- `max_tool_calls`
- `max_external_queries`
- `max_new_proposals`
- `max_runtime_seconds`
- `max_cost_usd`

Purpose:

- stop runaway agent loops
- control external-source usage
- limit proposal spam
- keep scheduled research cycles bounded

Budgets should be:

- attached to harness templates
- overridable per schedule or run when policy allows
- enforced in middleware or harness control flow, not just prompt text

## Hypothesis And Mechanism Ranking

The system should not generate unranked hypothesis floods.

Add a ranking layer based on:

- support claim count
- evidence quality
- path confidence
- contradiction count
- novelty relative to existing graph claims
- domain priors where available

Use the ranking layer in:

- `ContinuousLearningHarness`
- `MechanismDiscoveryHarness`
- hypothesis proposal review

## Research-Space Memory Model

The graph is only part of what the model needs to operate well.

### Graph memory

Lives in `services/artana_evidence_db`:

- claims
- evidence
- provenance
- relations
- reasoning paths

### Harness memory

Lives in Artana workspace state and artifacts:

- research objective
- structured research state
- current plan
- graph summary
- graph context snapshot
- run summaries
- chat summaries
- schedule history
- open questions
- candidate claims not yet applied

### Suggested artifacts

- `research_brief`
- `graph_summary`
- `graph_context_snapshot::<run_id>`
- `chat_summary::<session_id>`
- `delta_report::<cycle_id>`
- `candidate_claim_pack::<run_id>`
- `mechanism_candidates::<run_id>`
- `mechanism_score_report::<run_id>`
- `next_questions`

## Example Artana Usage

### Example 1: Bootstrap run

```text
POST /v1/spaces/{space_id}/agents/research-bootstrap/runs
-> create Artana run_id
-> worker acquires lease
-> ResearchBootstrapHarness runs
-> artifacts written
-> candidate claims written to proposal store
-> graph-write proposals created only after verification
-> run pauses if approval is required
-> resume continues same run
```

### Example 2: Chat question

```text
POST /v1/spaces/{space_id}/chat-sessions/{session_id}/messages
-> GraphChatHarness loads workspace snapshot + graph context
-> answer from graph first
-> optional PubMed refresh if needed
-> answer artifact and chat summary updated
-> optional graph-write proposal returned
```

### Example 3: Scheduled cycle

```text
schedule fires
-> artana_evidence_api enqueues run
-> worker acquires run lease
-> ContinuousLearningHarness runs
-> compares new evidence against current graph
-> updates research state and graph snapshot
-> writes delta report artifact
-> creates ranked candidate graph updates in proposal store
```

## Proposed API Surface

### Runtime endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service liveness. |
| `GET` | `/v1/harnesses` | List available harness templates. |
| `GET` | `/v1/harnesses/{harness_id}` | Describe one harness and its tools. |
| `POST` | `/v1/spaces/{space_id}/runs` | Start a generic harness run. |
| `GET` | `/v1/spaces/{space_id}/runs` | List runs for one space. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}` | Get one run summary. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/progress` | Get run progress. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/events` | Stream or page run events. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/resume` | Resume a paused run. |

### Approval endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/intent` | Record intent plan. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/approvals` | List approvals. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}` | Approve or reject gated action. |

### Artifact endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts` | List artifacts for a run. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts/{key}` | Fetch one artifact. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/workspace` | Fetch workspace snapshot. |

### Proposal endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/proposals` | List candidate claims, hypotheses, and mechanism candidates. |
| `GET` | `/v1/spaces/{space_id}/proposals/{proposal_id}` | Fetch one proposal with evidence and ranking. |
| `POST` | `/v1/spaces/{space_id}/proposals/{proposal_id}/promote` | Promote reviewed proposal into graph claim flow. |
| `POST` | `/v1/spaces/{space_id}/proposals/{proposal_id}/reject` | Reject proposal without touching graph ledger. |

### Chat endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/chat-sessions` | List chat sessions. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions` | Create chat session. |
| `GET` | `/v1/spaces/{space_id}/chat-sessions/{session_id}` | Fetch chat session state. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/messages` | Send message and run chat harness. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write` | Convert chat findings into graph proposals. |

### Schedule endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/schedules` | List schedules. |
| `POST` | `/v1/spaces/{space_id}/schedules` | Create schedule. |
| `GET` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Fetch schedule and recent runs. |
| `PATCH` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Update schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/pause` | Pause schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/resume` | Resume schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/run-now` | Trigger immediate cycle. |

### Opinionated workflow endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/research-bootstrap/runs` | Bootstrap a research space. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-search/runs` | Start graph search run. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-connections/runs` | Start graph-connection discovery run. |
| `POST` | `/v1/spaces/{space_id}/agents/hypotheses/runs` | Start hypothesis-generation run. |
| `POST` | `/v1/spaces/{space_id}/agents/continuous-learning/runs` | Start one learning cycle manually. |
| `POST` | `/v1/spaces/{space_id}/agents/mechanism-discovery/runs` | Start mechanism discovery run. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-curation/runs` | Start curation run. |

## Use Cases And User Stories

### Use case 1: Bootstrap a new research space

Story:

- researcher selects a research space
- enters a topic of study
- system searches PubMed and other sources
- extraction builds claims and evidence
- candidate claims are stored in proposal store
- reviewed proposals are promoted into graph claim flow
- research space now has initial memory

### Use case 2: Ask a question in chat

Story:

- researcher opens a chat session
- asks a question about the topic
- system reads graph memory first
- optionally checks new literature
- returns grounded answer with evidence

### Use case 3: Continuous learning

Story:

- researcher enables daily schedule
- system revisits what is known
- asks next best question
- searches for new evidence
- writes delta report and proposes new graph knowledge

### Use case 4: Discover a new mechanism

Story:

- researcher starts from a phenotype, pathway, or gene cluster
- system reads reasoning paths and nearby graph structure
- system groups converging paths through shared intermediate biology
- ranked mechanism candidates are produced
- top candidates become reviewable hypotheses, not canonical relations

### Use case 5: Governed curation

Story:

- curator reviews candidate claims
- agent prepares recommended actions
- high-risk changes pause for approval
- curator approves
- run resumes and applies allowed updates

## Implementation Phases

### Phase 1: Service foundation

- scaffold `services/artana_evidence_api`
- wire Artana `PostgresStore`
- move Artana and OpenAI runtime wiring out of `services/artana_evidence_db`
- add `health`, `runs`, `artifacts`, and `harnesses` endpoints
- add tool registry and graph client adapters
- add research state model and proposal store schema
- add architecture checks so `services/artana_evidence_db` cannot import Artana or model ports
- implement `ResearchBootstrapHarness`

### Phase 2: Chat and memory

- add chat-session persistence and APIs
- implement `GraphChatHarness`
- add workspace snapshot injection and artifact conventions
- add graph context snapshot capture
- add grounded-answer verification gates

### Phase 3: Scheduling and continuous learning

- add schedule definitions and scheduler worker
- implement `ContinuousLearningHarness`
- add run budgets and guardrails
- add proposal ranking
- add delta reports, next-question backlog, and recurring cycle history

### Phase 4: Mechanism discovery

- implement `MechanismDiscoveryHarness`
- add convergence scoring and mechanism candidate artifacts
- add mechanism proposal review flow

### Phase 5: Governed curation

- implement `ClaimCurationHarness`
- add approval flows, intent plans, and policy-gated graph writes
- add duplicate, conflict, and invariant checks

### Phase 6: Supervisor and advanced orchestration

- add `SupervisorHarness` where workflows require composition
- add richer multi-step programs across bootstrap, chat, and curation

## Validation Strategy

### Unit tests

- tool adapters
- harness registry
- policy decisions
- artifact conventions
- research state transitions
- proposal store promotion rules
- budget enforcement
- ranking logic

### Integration tests

- service endpoints
- Artana run lifecycle
- approval pause and resume
- scheduler to worker execution
- graph snapshot capture
- proposal promotion into graph claim flow
- supervisor parent-child pause and resume

### End-to-end tests

- bootstrap -> graph proposal
- chat -> grounded answer
- schedule -> delta report
- mechanism discovery -> ranked candidates
- curation -> approval -> resume -> apply
- supervisor -> bootstrap -> chat -> curation

### Quality gates

- `make test`
- `make type-check`
- service-local OpenAPI export and contract checks

## Rollout Strategy

Start with a forward-only v1:

1. bootstrap research space
2. read-only graph chat
3. proposal store, research state, and graph snapshots
4. schedules and continuous learning
5. mechanism discovery
6. governed curation writes

Do not add fallback paths or compatibility shims unless a real deployment need
appears later.

## Recommended Decisions

### 1. Scheduler model

Recommendation:

- use an external scheduler or a thin scheduler service layer to trigger runs
- use Artana workers for durable execution, leasing, pause or resume, and
  recovery

Why:

- Artana docs explicitly support external scheduler integration and multi-worker
  leasing
- Artana is strong at durable execution once a run exists
- timing, monitoring, retry policy, and cron-style triggering are cleaner when
  separated from harness execution

Practical v1:

- store schedule definitions in `artana_evidence_api`
- run a thin scheduler loop or external orchestrator that creates or enqueues
  Artana runs
- let stateless workers lease and execute those runs

### 2. Chat session storage model

Recommendation:

- use both Artana artifacts and service-local relational tables

Why:

- Artana artifacts are the right place for rich session memory:
  chat summary, answer evidence bundle, next questions, and workspace snapshot
- relational tables are better for UI and API listing:
  list sessions by space, sort by last activity, filter by status, and page
  results quickly

Practical split:

- relational table:
  `chat_sessions(id, space_id, title, created_by, created_at, updated_at,
  last_run_id, status)`
- Artana artifacts:
  detailed conversation memory, grounding bundles, summaries, and pending graph
  proposals

### 3. Auto-apply versus approval for graph mutations

Recommendation:

- do not auto-apply canonical graph mutations in v1
- require evidence-backed proposals first
- use the proposal store as the default landing zone for new AI-generated
  candidate knowledge
- require human approval for anything that can change claim status into
  materialized canonical graph state

Why:

- graph docs define claims as the authoritative ledger
- canonical relations are only projections of resolved support claims
- support claims need structured participants and claim evidence to materialize
- the canonical relation create endpoint is admin-gated and implemented by
  creating a manual support claim and materializing it

Safe v1 auto-apply candidates:

- harness artifacts
- chat summaries
- schedule metadata
- non-authoritative draft proposal records outside the graph system of record

Human approval required in v1:

- claim status changes that trigger materialization
- manual support claims intended to create canonical relations
- canonical relation creation or curation changes
- graph repair, rebuild, sync, and admin operations

Possible future relaxation:

- only after we have high-confidence verification, we could consider
  auto-creating reviewable non-canonical draft claims or hypotheses, but not
  canonical relations
