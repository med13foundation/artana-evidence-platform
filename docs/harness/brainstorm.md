# Harness Service Brainstorm

## Goal

Create a new standalone service under `services/` that uses the Artana kernel
and harness model to run durable AI workflows against the standalone graph
service.

Working assumption:

- `services/artana_evidence_db` remains the system of record for graph data and graph
  operations
- the new harness service orchestrates agents and governed tool execution
- the harness service talks to the graph service over HTTP through typed
  clients/tools, not through direct graph-table ownership

Greenfield mode is active for this design:

- one forward path
- no compatibility shims
- no migration or fallback behavior unless we explicitly decide to add it later

## Why A Separate Service

The graph service already owns:

- graph CRUD and graph read models
- claim-first write semantics
- graph control-plane operations
- graph-specific authz and space membership

The harness service should own:

- durable agent runs
- workspace state, artifacts, and outcomes
- approval and resume workflows
- governed tool execution against graph APIs
- agent-specific orchestration for graph curation, search, reasoning, and ops

This keeps the boundary clean:

- graph service = authoritative graph API
- harness service = durable AI control plane

## Source Constraints From Existing Docs

From `docs/artana-kernel`:

- prefer `StrongModelAgentHarness` and domain harness templates for app-facing
  orchestration
- use `KernelPolicy.enforced_v2()` for governed side-effect tools
- expose run lifecycle concepts such as status, progress, resume points,
  artifacts, checkpoints, and streaming progress
- support human approval flow:
  `ApprovalRequiredError -> approve -> resume -> retry`
- keep replay and step-key semantics deterministic

From `docs/graph`:

- the graph service is already standalone and HTTP-first
- claims are authoritative; canonical relations are derived projections
- graph control-plane and repair endpoints already exist
- graph search, graph connections, reasoning paths, hypotheses, and dictionary
  governance are already available as graph APIs

## Service Boundary

Recommended service name:

- `services/artana_evidence_api`

Alternative names:

- `services/harness_api`
- `services/agent_control_api`

Recommended ownership:

- owns harness runtime, Artana state, run metadata, policy wiring, and agent
  configuration
- does not own graph persistence, graph projections, or graph membership truth
- consumes graph APIs through a dedicated graph client/tool layer

## Intelligence And Tooling Model

The service should make a hard distinction between:

- intelligence side
  harnesses, agents, prompts, skills, planning, decision-making, and run
  orchestration
- deterministic side
  typed tools that call graph APIs, PubMed or other source APIs, extraction
  services, and governed write actions

This boundary needs to be explicit so the system remains inspectable and safe.

The expected mental model is:

```text
Research space
-> harness or agent selects next action
-> skill or policy shapes tool choice
-> deterministic tool executes typed operation
-> result returns to harness
-> harness decides next step
-> governed writes pause for approval when needed
```

The agent should not "know the system magically."
It should have a clear, constrained operating surface:

- available tools
- tool purpose
- tool risk level
- tool input and output contract
- when a skill should be used
- when approval or intent is required

## Harness Engineering Interpretation

Important correction:

In the newer literature, "harness engineering" is broader than just
"a harness that runs an agent."

The strongest interpretation from the OpenAI and Martin Fowler pieces is that a
harness is the full engineered environment around the model:

- structured context and knowledge sources
- constrained architecture and deterministic boundaries
- explicit tool surfaces
- observability and feedback loops
- verification and evaluation
- recurring cleanup and anti-entropy processes
- human steering and approval where needed

For this project, that means `artana_evidence_api` should not be designed as only
"the service that hosts agents." It should be designed as the runtime center of
an entire research harness system.

## What Harness Engineering Changes In This Design

### 1. Research Space Knowledge Must Be The System Of Record

The OpenAI article strongly argues for repository-local, structured knowledge as
the effective system of record for agents, because what the agent cannot see
"doesn't exist" from its operating perspective.

Applied here:

- each research space needs structured, durable, agent-readable memory
- that memory should include:
  graph state, run artifacts, chat summaries, schedule history, current
  objectives, open questions, and operating rules
- the graph is only part of the harness knowledge base

So the full research harness memory should likely include:

- graph knowledge in `artana_evidence_db`
- workspace state and artifacts in `artana_evidence_api`
- explicit markdown or structured plans for longer-running research programs

### 2. Agent Legibility Is A Product Requirement

OpenAI’s piece emphasizes agent legibility, not just human legibility.

Applied here:

- the agent needs a clean map of:
  research space goals, available tools, source policies, graph write rules,
  approval rules, and current unknowns
- the harness should prefer:
  small stable entrypoints, indexed docs, typed schemas, and explicit workflow
  states
- avoid giant generic prompts that try to encode the entire system in one place

This supports:

- short top-level harness instructions
- deeper structured docs and registries behind them
- explicit tool and skill registries

### 3. Deterministic Constraints Matter More Than Clever Prompting

OpenAI and Fowler both point toward the same principle:

- let the model work inside rigid, enforceable boundaries
- do not rely on prompt cleverness alone

Applied here:

- graph mutation rules must be enforced by code, not by prompt etiquette
- tool visibility should be workflow-specific
- graph writes should follow typed proposal and approval pipelines
- schedule behavior should be explicit and inspectable
- data boundaries should be validated at ingress and egress

This reinforces the split we already discussed:

- intelligence chooses
- deterministic systems constrain and verify

### 4. Verification Must Be First-Class

Fowler’s main critique of the OpenAI write-up is useful:

- internal quality is not enough
- functional and behavioral verification must be explicit

Applied here:

- a research answer should be checked for grounding:
  what claims, evidence, and sources support it
- a proposed graph write should be checked for:
  schema validity, duplication, claim lineage, and policy compliance
- a scheduled learning run should produce:
  a delta report, not just more text

This suggests every major harness should end in a verification phase such as:

- evidence grounding check
- duplicate or conflict check against existing claims
- policy evaluation
- write proposal review or auto-approval eligibility test

### 5. Anti-Entropy Loops Are Part Of The Harness

OpenAI’s article is explicit that background cleanup is part of the harness.

Applied here:

- recurring maintenance should not only search for new papers
- it should also detect:
  stale objectives, duplicated claims, low-quality summaries, broken links
  between artifacts and graph state, and outdated research-space guidance

So scheduled jobs should likely include two families:

- learning jobs
  find new evidence and propose new knowledge
- garbage-collection jobs
  clean drift, stale summaries, and weak structured context

### 6. Harnesses May Become Service Templates

Fowler’s suggestion that harnesses could evolve into service-template-like
golden paths is directly relevant.

Applied here:

- we may want a standard harness template per workflow:
  research bootstrap, chat, continuous learning, curation, ops
- each template should bundle:
  allowed tools, skills, verification steps, approval rules, artifact schema,
  and run stages

That is a stronger design than treating each workflow as a one-off prompt.

## Updated Design Principle

The key design principle should be:

- do not just build agent endpoints
- build a research harness system

That system includes:

- agents and prompts
- harness runtimes
- tool registries
- skill packs
- deterministic guards
- verification stages
- schedule and anti-entropy jobs
- durable research-space memory
- approval and governance flows

## Harness Strategy Options

There are two viable architecture shapes.

### Option A: One Supervisor Harness For The Full Cycle

Shape:

- one top-level research harness owns the whole lifecycle
- it can invoke child steps or child agents internally
- it has the full view of research space state, graph memory, schedules, and
  chat context

Pros:

- unified run model
- simpler top-level UX
- easier to express an end-to-end research loop

Risks:

- one harness can become too broad
- prompt and skill management may become harder over time
- harder to reason about which tools should be visible in each phase

### Option B: A Collection Of Specialized Harnesses Or Agents

Shape:

- `ResearchBootstrapHarness`
- `GraphChatHarness`
- `ContinuousLearningHarness`
- `ClaimCurationHarness`
- `GraphOpsHarness`
- optional `SupervisorHarness` above them

Pros:

- narrower tool surfaces
- easier to test and reason about
- better fit for different risk profiles
- easier to attach different skills and policies by workflow

Risks:

- requires stronger orchestration between harnesses
- more run types and more UI states to present

### Current Recommendation

Use specialized harnesses plus one supervisor layer when needed.

That means:

- the user sees simple product workflows
- internally each workflow has a focused harness with a constrained tool set
- a supervisor can compose them later for larger end-to-end flows

This is the cleaner long-term design for a governed research system.

## Tool Collections And Skills

The system should expose tools as explicit capability packs, and skills should
teach the intelligence layer how to use those packs well.

Think in terms of:

- harness
  the runtime and workflow boundary
- tools
  deterministic operations available to that workflow
- skills
  reusable instructions for when and how to use a subset of tools

Example:

- a `GraphChatHarness` may have graph-read tools, artifact-read tools, and
  optional fresh-retrieval tools
- a `ContinuousLearningHarness` may have graph-read tools, source-discovery
  tools, extraction tools, and governed graph-write proposal tools
- a `GraphOpsHarness` may have only admin-grade audit and repair tools

Skills can help the agent with patterns such as:

- how to investigate a research question
- when to trust graph memory versus fetch fresh literature
- how to compare new evidence against existing claims
- how to prepare a graph-write proposal instead of writing directly
- how to run a scheduled refresh without repeating prior work

## Proposed Tool Taxonomy

### 1. Graph Read Tools

Examples:

- graph search
- graph document
- neighborhood view
- domain views
- claim reads
- reasoning path reads

Purpose:

- inspect current research-space memory

### 2. External Research Tools

Examples:

- PubMed query generation
- PubMed search
- source discovery
- content enrichment
- full-text acquisition where allowed

Purpose:

- find new external evidence

### 3. Knowledge Construction Tools

Examples:

- entity recognition
- extraction
- graph connection discovery
- hypothesis generation
- claim comparison

Purpose:

- turn raw source material into graph-ready structured knowledge

### 4. Graph Write Proposal Tools

Examples:

- create candidate claims
- create candidate evidence bundles
- create candidate graph updates
- prepare curation packets

Purpose:

- prepare structured proposals before mutation

### 5. Governed Mutation Tools

Examples:

- patch claim status
- create claim relations
- create manual hypotheses
- create manual support claims
- trigger admin repair or rebuild operations

Purpose:

- apply approved changes to the system of record

### 6. Workspace And Memory Tools

Examples:

- read prior run artifacts
- read schedule history
- write checkpoints
- save summaries
- open related chat context

Purpose:

- give the harness durable continuity across runs and sessions

## Tool Visibility Rules

Not every harness should see every tool.

Recommended rule:

- each harness gets a minimum necessary tool set
- tool visibility is declared in the harness registry
- skills are attached per harness, not globally by default
- high-risk tools are excluded from read-only workflows entirely
- admin tools are only visible to admin workflows

This reduces prompt sprawl and prevents the intelligence layer from operating
with an unnecessarily broad action surface.

## Deterministic Contract Requirements For Tools

Every tool exposed to a harness should declare:

- name
- purpose
- input schema
- output schema
- side-effect flag
- risk level
- required capability
- approval behavior
- semantic idempotency policy if applicable

The harness service should also expose capability introspection so the runtime
and UI can inspect:

- which tools were visible for a run
- why some tools were filtered
- which skill pack or policy pack shaped the run

## Primary Use Cases

1. Start a research program for a selected research space and gather external
   evidence from PubMed and other supported sources.
2. Convert acquired source material into graph claims, participants, evidence,
   and canonical projections where appropriate.
3. Open chat sessions inside that research space and ask questions against the
   accumulated graph knowledge.
4. Let the system optionally check external sources again before answering so
   new evidence can be incorporated when relevant.
5. Feed validated new findings from chat-driven research back into the graph as
   future knowledge.
6. Run curation, governance, and graph-maintenance workflows as needed.
7. Schedule recurring research runs so the system keeps learning about a topic
   over time without requiring a human to restart the process manually.

## Proposed End-To-End Product Loop

This feels like the right top-level experience:

1. The researcher creates or selects a `research space`.
2. The researcher defines the topic of study:
   disease area, gene set, phenotype cluster, mechanism question, or broader
   domain objective.
3. A research harness starts an acquisition workflow:
   PubMed search, source discovery, enrichment, extraction, and graph
   construction.
4. The graph becomes the durable memory for that research space:
   entities, claims, evidence, relations, provenance, and reasoning artifacts.
5. The researcher opens one or more chat sessions inside the same research
   space.
6. Each chat session answers questions from:
   existing graph knowledge first, plus optional fresh external retrieval when
   needed.
7. If the chat session discovers new evidence or new candidate claims, the
   system can propose adding them back into the graph.
8. Curators or researchers review any gated write actions.
9. The graph improves over time, so later chats start from stronger prior
   knowledge instead of redoing all research from zero.
10. Scheduled research jobs keep revisiting the topic, looking for new evidence,
    new claims, and changes in the literature over time.

This makes the harness service more than a run launcher. It becomes the
orchestration layer for a continuous research loop:

- research space selection
- evidence acquisition
- graph building
- conversational questioning
- incremental graph enrichment
- scheduled continuous learning

## User Stories

### Researcher Stories

1. As a researcher, I want to start with a research space and topic of study so
   all future work is scoped to a coherent knowledge area.
2. As a researcher, I want the system to search PubMed and other sources for
   that topic so I do not have to manually collect every paper first.
3. As a researcher, I want the system to convert gathered evidence into graph
   claims and explainable relations so the research space accumulates knowledge
   over time.
4. As a researcher, I want to open chat sessions against that research space so
   I can ask follow-up questions in natural language.
5. As a researcher, I want the chat agent to answer using the existing graph
   first, and then optionally check for new external evidence when needed.
6. As a researcher, I want useful new findings from a chat session to be
   proposed back into the graph so the system keeps learning.
7. As a researcher, I want to come back later and see the prior runs, chat
   sessions, and graph artifacts for that same research space.
8. As a researcher, I want to schedule daily or periodic research refreshes so
   the system keeps looking for new evidence in my topic area.
9. As a researcher, I want the scheduled agent to use what is already known in
   the graph to ask better next questions instead of repeating the same search
   forever.

### Curator Stories

1. As a curator, I want an agent to gather open claims, participants, and
   evidence into one review workspace so I can resolve claims faster.
2. As a curator, I want the agent to propose claim status changes before
   applying them so I can review the reasoning before any graph mutation
   happens.
3. As a curator, I want high-risk graph actions to pause for approval so I can
   control canonical-graph changes explicitly.
4. As a curator, I want a run history for each curation workflow so I can audit
   what the agent saw, suggested, and changed.

### Graph Admin Stories

1. As a graph admin, I want to launch readiness audits and repair workflows from
   a harness UI so I can manage graph health without manual scripts.
2. As a graph admin, I want admin-grade operations to require intent and
   approval so dangerous maintenance actions are deliberate and traceable.
3. As a graph admin, I want to inspect active, paused, failed, and completed
   runs across spaces so I can monitor service health and intervene when needed.
4. As a graph admin, I want operation outputs saved as durable artifacts so I
   can review what was repaired or rebuilt after the run completes.
5. As a graph admin, I want visibility into scheduled research jobs so I can
   monitor failures, drift, and stale spaces.

### Governance Stories

1. As a governance reviewer, I want the agent to propose dictionary or concept
   changes with rationale and evidence so I can approve or reject them with
   context.
2. As a governance reviewer, I want the system to separate read-only analysis
   from write actions so proposals can be inspected safely before mutation.
3. As a governance reviewer, I want approval decisions and resumes to be
   explicit steps in the workflow so policy-sensitive changes remain auditable.

## Expected User Experience

The new service should feel like a durable agent workspace, not like a raw job
queue.

### Entry Experience

The first thing a researcher does is not "start a run." The first thing they do
is choose the research space they are working in.

That suggests the UX should begin with:

1. select research space
2. define or refine topic of study
3. choose an initial agent action:
   bootstrap research, explore graph, or open a chat session

### Research Space Bootstrap Experience

For a new topic, the UI should guide the user through a bootstrap flow.

The user enters:

- research topic or question
- optional seed entities, terms, or source constraints
- optional depth or coverage target

The system then starts a long-running research bootstrap harness that:

- generates source queries
- searches PubMed and other configured sources
- enriches and extracts structured knowledge
- writes claims and evidence into the graph
- materializes canonical relations where rules allow
- produces a research-space summary artifact

At the end of this flow, the user should feel that the research space now has a
real starting knowledge base.

### Continuous Learning Experience

Once a research space has an initial graph, the user should be able to turn on
continuous research for that space.

The user configures:

- schedule:
  daily, weekly, or another supported interval
- research objective:
  what the recurring agent should keep tracking
- optional question strategy:
  fixed recurring question, or "derive the next best question from what we know
  so far"
- optional source scope:
  PubMed only, or PubMed plus other approved sources

The system then runs a recurring harness that:

- reads the current graph state for the research space
- inspects what has already been learned
- generates one or more next-step questions
- searches external sources for new evidence
- compares new evidence against existing claims and artifacts
- proposes or writes new claims back into the graph under policy controls
- emits a run summary for that scheduled cycle

This should feel like the system is continuously studying the topic, not just
waiting for the next manual prompt.

### Core UX Pattern

1. The user chooses a research space.
2. The user starts either:
   a bootstrap research workflow, a targeted analysis workflow, or a chat
   session.
3. The user can also enable a scheduled research workflow for ongoing topic
   monitoring.
4. The UI shows a short form with the minimum required inputs:
   question, topic, seed entities, target space, risk level, and optional run
   label.
5. The user starts the run or chat and immediately receives a run page or chat
   workspace.
6. The run page or chat workspace shows:
   current status, progress stage, recent events, visible tools, and produced
   artifacts.
7. If the workflow is read-only, it should usually complete without interruption and
   produce a final answer plus evidence bundle.
8. If the workflow needs approval, it pauses with a clear action card:
   what action is being requested, why it is gated, and what will happen after
   approval.
9. After approval, the run resumes in place and keeps the same run history.
10. When the run completes, the UI shows a stable outcome page with:
   summary, evidence, graph links, and downloadable artifacts.

### Chat Session Experience

Chat should be a first-class surface in this service, not an afterthought.

The expected behavior:

1. The user opens a chat inside one research space.
2. The chat agent has access to:
   prior graph knowledge, prior run artifacts, and optionally external retrieval
   tools.
3. For each question, the agent should decide:
   answer from the graph only, or retrieve fresh sources before answering.
4. The answer should include:
   response text, supporting claims, evidence, provenance, and any newly found
   material.
5. If new candidate knowledge is discovered, the chat can propose:
   add these claims to the graph, create a hypothesis, or schedule a deeper
   research run.
6. Any graph write remains explicit and governed.

This makes chat a research companion layered on top of durable graph memory,
not a stateless chatbot.

### Scheduled Research Experience

Scheduling should be a first-class user feature.

The expected behavior:

1. The user enables recurring research for one research space.
2. The user chooses a cadence and objective.
3. Each scheduled run starts from existing graph memory and prior artifacts.
4. The scheduled agent asks:
   what do we know, what is uncertain, what has changed, and what is the next
   high-value question to investigate?
5. The scheduled run searches approved external sources and gathers new
   evidence.
6. The run produces:
   a delta report, new candidate claims, updated evidence bundles, and optional
   proposed graph writes.
7. The user can inspect each scheduled cycle and compare it against prior runs.

This should feel like standing research coverage for the topic.

### What The UI Should Show For Each Run

- run title and harness type
- initiating user and graph space
- related chat session, if the run was created from chat
- schedule metadata, if the run was created by a recurring job
- run status:
  `active`, `paused`, `failed`, or `completed`
- current stage and percent complete
- recent model and tool activity summaries
- generated artifacts such as answer, claim review pack, reasoning path pack,
  or ops report
- delta artifacts for scheduled runs such as:
  new papers found, new claims proposed, changed evidence, and unanswered next
  questions
- pending approvals, if any
- final outcome with rationale and linked graph resources

### Example UX Flows

#### 1. Graph Search Experience

The user enters:

- a natural-language question
- optional entity filters
- optional request for a graph document or reasoning path expansion

The UI returns:

- a run screen with live progress
- a final answer card
- supporting evidence and provenance
- links into graph views, graph documents, or claim overlays

This should feel closer to "ask the graph and inspect why" than "submit a
background task."

#### 2. Research Chat Experience

The user opens a chat within one research space and asks:

- what is known already?
- what evidence supports this?
- has anything new appeared in PubMed since the last run?
- should we add this new paper or claim into the graph?

The UI returns:

- conversational answers grounded in the graph
- clear citations and provenance
- optional notices when fresh external retrieval was used
- action buttons to launch deeper runs or propose graph updates

This should feel like a persistent research notebook with agent assistance.

#### 3. Claim Curation Experience

The user enters:

- target space
- optional entity or claim focus
- curation mode such as review-only or review-and-apply

The UI returns:

- a prioritized queue of claims the agent reviewed
- suggested actions with rationale
- explicit approval cards for any mutating step
- a final curation summary with changed claims and skipped claims

This should feel like an assisted review workstation.

#### 4. Graph Ops Experience

The admin enters:

- operation type such as readiness audit, repair, or reasoning rebuild
- scope such as one space or global
- optional dry-run behavior if we choose to support that later

The UI returns:

- operation progress with clear stages
- warnings, blocked items, and approval requests
- a final report artifact with counts, affected resources, and next actions

This should feel like a governed maintenance console, not a shell-script proxy.

#### 5. Scheduled Research Experience

The researcher configures:

- the research space
- the recurring question or objective
- schedule cadence
- allowed sources
- whether new graph writes should be proposed only or auto-applied under policy

The UI returns:

- a schedule detail page
- the history of all scheduled runs
- per-run delta summaries
- alerts for failed runs or pending approvals

This should feel like a subscription to ongoing learning for that topic.

### UX Principles

- research space is the top-level container for both graph and chat activity
- chat should build on durable graph memory, not replace it
- external retrieval should be available when the graph may be stale or
  incomplete
- newly discovered knowledge should have a clear path back into the graph
- recurring research should improve the space incrementally, not reset context
- every run must be resumable
- every important step must be inspectable
- writes must be visibly gated
- final outputs must link back to graph resources
- users should not need to understand Artana internals to use the product
- advanced runtime details should be available, but not required, in the
  default UI

## Candidate Harness Types

### 1. Graph Search Harness

Purpose:

- answer natural-language graph questions
- call graph search, graph document, neighborhood, and reasoning-path endpoints
- return evidence-backed answer plus saved artifacts

Likely tools:

- `graph.search`
- `graph.document`
- `graph.neighborhood`
- `graph.reasoning_paths.get`

### 2. Graph Curation Harness

Purpose:

- review claims, participants, evidence, and conflicts
- suggest or apply claim triage actions
- optionally create manual support claims or claim relations

Likely tools:

- `graph.claims.list`
- `graph.claims.by_entity`
- `graph.claims.evidence`
- `graph.claims.patch`
- `graph.claim_relations.create`
- `graph.relations.create_manual`

### 3. Graph Operations Harness

Purpose:

- audit projection readiness
- trigger repair operations
- rebuild reasoning paths
- monitor operation runs

Likely tools:

- `graph.admin.readiness`
- `graph.admin.repair`
- `graph.admin.reasoning_rebuild`
- `graph.admin.operation_runs`

### 4. Graph Governance Harness

Purpose:

- inspect dictionary entities, relation types, variables, transforms, and
  concept policy
- propose governed changes for admin approval

Likely tools:

- `graph.dictionary.search`
- `graph.dictionary.relation_constraints`
- `graph.dictionary.variables`
- `graph.concepts.policy`
- `graph.concepts.decisions.propose`

### 5. Supervisor Harness

Purpose:

- compose multiple child harnesses for larger workflows
- example: search -> curation -> graph ops -> summary artifact

Artana fit:

- `SupervisorHarness` coordinating child `StrongModelAgentHarness` runs

## API Shape

The service should have two layers of endpoints:

1. Generic harness-runtime endpoints
2. Opinionated graph-agent entrypoints built on top of the generic runtime

### A. Runtime Foundation Endpoints

These are close to Artana kernel and harness lifecycle concepts.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check for the harness service. |
| `GET` | `/v1/harnesses` | List registered harness templates and tool sets. |
| `GET` | `/v1/harnesses/{harness_id}` | Describe one harness template, policies, and required inputs. |
| `POST` | `/v1/spaces/{space_id}/runs` | Start a run from a harness template. |
| `GET` | `/v1/spaces/{space_id}/runs` | List runs for one graph space. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}` | Fetch run metadata, status, and outcome summary. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/progress` | Fetch deterministic run progress. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/resume-point` | Inspect the current pause or resume boundary. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/events` | Read event or summary history, optionally from `since_seq`. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/resume` | Resume a paused run. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/block` | Block a run for operator intervention. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/unblock` | Clear a block. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts` | List durable run artifacts. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts/{key}` | Fetch one artifact. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/workspace` | Fetch current workspace state. |

### B. Approval And Safety Endpoints

These map to the `enforced_v2` safety workflow.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/intent` | Record or update a typed intent plan for the run. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/approvals` | List pending and completed approvals. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}` | Record human approval or rejection. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/capabilities` | Show visible tools and capability filtering. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/policy-decisions` | Inspect safety-policy allow or deny summaries. |

### C. Opinionated Agent Endpoints

These give product-level entrypoints without forcing callers to know the full
runtime model.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/graph-search/runs` | Start a graph-search harness run. |
| `POST` | `/v1/spaces/{space_id}/agents/research-bootstrap/runs` | Start a research-space bootstrap harness run. |
| `POST` | `/v1/spaces/{space_id}/agents/chat-sessions` | Create a chat session bound to one research space. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-curation/runs` | Start a claim-curation harness run. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-ops/runs` | Start a graph-maintenance harness run. |
| `POST` | `/v1/spaces/{space_id}/agents/graph-governance/runs` | Start a governance harness run. |
| `POST` | `/v1/spaces/{space_id}/agents/reasoning/runs` | Start a mechanism or path-exploration harness run. |

### D. Chat And Scheduling Endpoints

These support persistent chat and recurring research.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/chat-sessions` | List chat sessions for one research space. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions` | Create one chat session. |
| `GET` | `/v1/spaces/{space_id}/chat-sessions/{session_id}` | Fetch one chat session and its state. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/messages` | Send one user message and trigger an agent response. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write` | Propose adding chat-derived findings back into the graph. |
| `GET` | `/v1/spaces/{space_id}/schedules` | List recurring research schedules for one space. |
| `POST` | `/v1/spaces/{space_id}/schedules` | Create one recurring research schedule. |
| `GET` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Fetch one schedule definition and recent run history. |
| `PATCH` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Update one schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/pause` | Pause one recurring schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/resume` | Resume one recurring schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/run-now` | Trigger the schedule immediately. |

## Tool Boundary

The harness service should not reimplement graph business logic. It should wrap
graph HTTP endpoints as Artana tools.

Tool categories:

- read tools
  graph search, graph document, neighborhood, claim reads, reasoning-path reads
- external research tools
  PubMed search, source discovery, content enrichment, extraction, and source
  comparison
- low-risk write tools
  create concept proposal, create manual hypothesis, create claim relation
- high-risk write tools
  patch claim status, create canonical relation, repair projections, rebuild
  reasoning paths, sync graph spaces

Policy expectation:

- read tools can usually run without approval
- low-risk write tools require intent plus semantic idempotency
- high-risk write tools require intent, limits, and explicit approval

## Auth And Multi-Tenancy

Baseline model:

- every run is scoped to `space_id`
- caller identity is passed through to the graph service where needed
- harness service enforces its own access rules for starting or approving runs

Candidate access levels:

- `member`
  can start read-only graph-search or reasoning runs
- `researcher+`
  can start curation or low-risk write workflows
- `graph_admin`
  can start graph-ops workflows and approve high-risk admin actions

Open design question:

- should the harness service define its own `harness_admin` claim, or should it
  reuse graph-space access plus `graph_admin` for dangerous operations?

## Persistence And Runtime

Recommended early shape:

- standalone FastAPI service under `services/artana_evidence_api`
- Artana state stored in a dedicated service schema or database
- graph service remains external and is reached over HTTP only
- harness service emits its own OpenAPI artifact and generated typed clients

Possible persistence split:

- Artana event/state store
- service-local registry tables for harness templates, agent configs, and run
  labels
- service-local schedule tables for recurring research definitions and execution
  metadata
- chat session tables or durable artifacts for research-space conversation state

Do not do in v1:

- direct reuse of graph DB tables as harness-owned state
- in-process calls into `services/artana_evidence_db`
- dual runtime modes for both direct-import and HTTP graph access

## Suggested Internal Modules

```text
services/artana_evidence_api/
├── app.py
├── main.py
├── config.py
├── auth.py
├── composition.py
├── dependencies.py
├── graph_client.py
├── scheduling.py
├── scheduler_registry.py
├── chat_sessions.py
├── harness_registry.py
├── policy.py
├── routers/
│   ├── health.py
│   ├── harnesses.py
│   ├── runs.py
│   ├── approvals.py
│   ├── artifacts.py
│   ├── agents.py
│   ├── chat.py
│   └── schedules.py
└── openapi.json
```

## Recommended MVP

### Phase 1

- scaffold `artana_evidence_api`
- wire Artana kernel with `enforced_v2`
- add generic run lifecycle endpoints
- add one `research-bootstrap` harness
- add one read-only `graph-search` harness
- add chat-session creation and message endpoints
- add recurring schedule definitions and a basic scheduler worker
- add streaming or polling progress endpoint

### Phase 2

- add approval and intent endpoints
- add one mutating `graph-curation` harness
- add graph HTTP tool wrappers with semantic idempotency
- persist run artifacts and outcomes cleanly

### Phase 3

- add `graph-ops` and `graph-governance` harnesses
- add supervisor workflows
- add richer admin observability and run inspection

## Questions To Resolve

1. Do we want one generic runtime API that powers the UI, or do we want the UI
   to use opinionated per-agent endpoints only?
2. Should runs be synchronous request-response starts plus later polling, or do
   we also want SSE or websocket streaming from day one?
3. Should approvals live in the harness service only, or should some graph-admin
   approvals also be recorded in graph-service operation history?
4. Is `graph-search` the first production harness, or is claim curation the
   higher-value first workflow?
5. Does the harness service need its own database from day one, or is a
   dedicated schema in the existing Postgres instance enough for the first cut?

## Current Recommendation

Start with `services/artana_evidence_api` as a separate standalone service that:

- treats the research space as the top-level user container
- supports both bootstrap research runs and persistent chat sessions
- supports recurring scheduled research for continuous learning
- uses Artana `StrongModelAgentHarness`
- treats `services/artana_evidence_db` as the only graph mutation and query boundary
- exposes generic run lifecycle endpoints first
- adds opinionated research, chat, and graph-agent entrypoints on top
- keeps all mutating graph tools behind `enforced_v2` policy and approval flows

That gives us a clean split:

- graph service owns knowledge
- harness service owns AI execution and conversational orchestration

## External Research Findings

The broader ecosystem points to a few recurring architecture patterns.

### 1. Durable Agent Runtime

What it is:

- an agent runtime with persisted state, resumability, interrupts, and memory

What official docs emphasize:

- LangGraph recommends durable execution, persistence, interrupts, memory, and
  specialized multi-agent patterns when one agent has too many tools or too
  much context
- the docs explicitly separate:
  skills, routers, and custom workflows
- they also emphasize wrapping side effects in replay-safe tasks and using
  thread-based persistence for long-lived conversations

Why it matters here:

- this maps closely to the harness layer we are describing
- it is a strong fit for chat sessions, approval pauses, resumable research
  runs, and specialized harnesses

Takeaway:

- use a persistent agent runtime for the intelligence layer
- keep each workflow bounded with a constrained tool surface

### 2. Durable Workflow Orchestration

What it is:

- a workflow engine for long-running, fault-tolerant jobs and schedules

What official docs emphasize:

- Temporal positions itself around crash-proof execution for workflows that
  must resume after failures or long delays
- Prefect emphasizes deployments, schedules, active or paused schedule state,
  and recurring flow runs created from cron, interval, or RRule schedules

Why it matters here:

- research bootstrap and recurring learning runs are workflow problems as much
  as they are agent problems
- if runs can last minutes, pause for approval, or recur every day, a workflow
  layer is valuable

Takeaway:

- use a workflow scheduler or durable run layer for recurring research and
  large bootstrap jobs
- do not rely on raw HTTP request lifetimes for long-running work

### 3. Lightweight Queue And Scheduler

What it is:

- a task queue plus periodic task scheduler

What official docs emphasize:

- Celery provides task workflows, monitoring, periodic tasks, crontab-based
  scheduling, and worker clusters
- Celery also warns that only one scheduler instance should control a schedule
  at a time to avoid duplicate executions

Why it matters here:

- this is the lighter-weight option if we do not want a full workflow engine
- it is good for background jobs and recurring refresh tasks
- it is weaker than a durable workflow engine for complex approval and replay
  semantics

Takeaway:

- Celery is a valid simpler option for v1 scheduling
- it is better for "run this job" than for deep durable orchestration

### 4. Standardized Tool Surface

What it is:

- a protocol or registry layer that exposes deterministic tools and resources
  to the intelligence system

What official docs emphasize:

- MCP separates tools, resources, and prompts into explicit discoverable
  primitives
- MCP tools are model-controlled and schema-defined
- MCP resources are application-driven and URI-addressable
- MCP explicitly recommends keeping a human in the loop for sensitive tool
  invocations
- OpenAI now supports remote MCP servers and background mode in the Responses
  API, which shows the ecosystem is converging around explicit tool surfaces and
  asynchronous agent execution

Why it matters here:

- this is very close to your idea of "agents on one side, deterministic tools
  on the other"
- graph endpoints, PubMed access, extraction, scheduling metadata, and artifact
  reads could all be exposed as typed tools or resources

Takeaway:

- make the tool surface explicit and schema-driven
- strongly consider MCP compatibility, even if the first implementation is
  internal

### 5. Graph-Grounded Retrieval

What it is:

- answering questions from a graph-backed memory system rather than from vector
  search alone

What official docs emphasize:

- Neo4j’s official GraphRAG package and guides focus on combining vector
  retrieval with graph traversal and graph-aware retrieval pipelines
- the knowledge graph builder pattern separates document ingestion, chunking,
  entity extraction, relation extraction, and graph-backed retrieval

Why it matters here:

- your product needs both:
  graph memory for known claims, and fresh source retrieval for new knowledge
- this argues against a chat architecture that only uses embeddings and raw
  document chunks

Takeaway:

- keep the graph as durable domain memory
- use hybrid retrieval:
  graph first, vector or document retrieval second, live web or PubMed refresh
  third

## Architecture Strategies Seen In Practice

Based on the sources, there are four realistic ways to build this.

### Strategy A: One Big Agent Service

Shape:

- one service
- one orchestrator agent
- broad tool access
- background jobs handled ad hoc

Benefits:

- fastest initial delivery

Drawbacks:

- weak boundaries
- tool sprawl
- harder approval and replay semantics
- usually degrades as the number of workflows grows

Fit:

- poor long-term fit for this product

### Strategy B: Agent Runtime Plus Workflow Scheduler

Shape:

- persistent harness or agent runtime for chat, approvals, memory, and tool use
- durable workflow layer for bootstrap and recurring research runs
- graph service remains the system of record

Benefits:

- strong fit for long-lived research spaces
- clear separation between conversational intelligence and recurring jobs
- better reliability for scheduled research

Drawbacks:

- more moving parts

Fit:

- strongest fit for this product

### Strategy C: Queue-Centric Background System

Shape:

- Celery-style workers and beat scheduler
- agents invoked as background jobs
- custom persistence built in application tables

Benefits:

- simpler operationally at the start
- good enough for batch refresh and extraction jobs

Drawbacks:

- more custom work for pause or resume, approval, and thread memory
- easier to end up with fragmented run state

Fit:

- acceptable v1 compromise if speed matters more than orchestration depth

### Strategy D: Model-Vendor-Managed Background Execution

Shape:

- rely heavily on model-provider background execution and built-in tools
- keep application orchestration thin

Benefits:

- less infrastructure for some long-running model steps

Drawbacks:

- less control over workflow semantics
- weaker fit for deep domain-specific audit, scheduling, graph write controls,
  and multi-service orchestration

Fit:

- good inside a step, not ideal as the primary system architecture

## Research-Backed Recommendation

Best-fit architecture for this project:

1. `services/artana_evidence_db`
   remains the system of record for graph knowledge and graph operations.
2. `services/artana_evidence_api`
   becomes the persistent agent runtime for:
   chat sessions, research runs, approvals, artifacts, and workspace memory.
3. use specialized harnesses rather than one giant agent:
   bootstrap, chat, continuous learning, curation, ops.
4. expose graph and research capabilities through a typed tool registry:
   preferably MCP-compatible or MCP-inspired.
5. use a durable scheduling layer for recurring research:
   Prefect-like or Temporal-like if durability matters strongly, Celery if we
   want a lighter first cut.
6. use hybrid retrieval:
   graph memory first, graph plus document retrieval next, fresh PubMed or web
   retrieval when needed.
7. keep write actions explicit:
   proposal first, governed mutation second.

Pragmatic interpretation:

- if we optimize for fastest v1:
  `artana_evidence_api + Celery + explicit tool registry`
- if we optimize for durable long-term correctness:
  `artana_evidence_api + durable workflow engine + explicit tool registry`

## External Sources

- LangChain multi-agent:
  https://docs.langchain.com/oss/python/langchain/multi-agent/index
- LangGraph durable execution:
  https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph persistence:
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph memory:
  https://docs.langchain.com/oss/javascript/langgraph/memory
- LangGraph interrupts:
  https://docs.langchain.com/oss/python/langgraph/interrupts
- Prefect schedules:
  https://docs.prefect.io/v3/concepts/schedules
- Celery introduction:
  https://docs.celeryq.dev/en/stable/getting-started/introduction.html
- Celery canvas workflows:
  https://docs.celeryq.dev/en/stable/userguide/canvas.html
- Model Context Protocol tools:
  https://modelcontextprotocol.io/specification/2025-03-26/server/tools
- Model Context Protocol resources:
  https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- OpenAI Responses API tools and background mode:
  https://openai.com/index/new-tools-and-features-in-the-responses-api/
- Neo4j GraphRAG:
  https://neo4j.com/docs/neo4j-graphrag-python/current/index.html
- Neo4j GraphRAG retrieval guide:
  https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html

## How To Achieve This With Artana

Using `docs/artana-kernel/docs`, the cleanest implementation is to treat Artana
as the durable execution substrate for the harness system, not as the graph
service itself.

### Artana Layer Mapping

Based on Chapter 1 and Chapter 6, Artana has three layers that matter here:

- `Kernel`
  durable execution, replay-safe model and tool steps, artifacts, checkpoints,
  event ledger, run status, and leases
- `AutonomousAgent`
  multi-turn reasoning on top of the kernel
- `Harness`
  structured long-running discipline, workspace state, outcomes, artifacts, and
  supervisor composition

For this product:

- graph persistence stays in `services/artana_evidence_db`
- research intelligence runs in Artana harnesses
- scheduling feeds Artana runs from outside or from a thin service-local
  scheduler layer

### Recommended Artana Building Blocks

#### 1. `StrongModelAgentHarness` For User-Facing Research Flows

Use this for:

- research bootstrap
- graph chat
- continuous learning
- claim curation

Why:

- the docs position `StrongModelAgentHarness` as the modern default when you
  want `AutonomousAgent` plus durable harness structure
- it already supports:
  `ContextBuilder`, artifacts, workspace state, outcomes, draft and verify
  loops, and acceptance gates

This is the best fit for:

- long-running research runs
- resumable chat-backed workflows
- tool-rich but governed model behavior

#### 2. Domain Templates For Workflow Shape

The docs already define domain templates such as:

- `ResearchHarness`
- `CurationHarness`
- `ReviewHarness`
- `ActionHarness`

That maps well to your product:

- `ResearchBootstrapHarness`
  derived from the research-shaped posture
- `GraphChatHarness`
  research-shaped with chat context and read-heavy tools
- `ContinuousLearningHarness`
  research-shaped plus scheduling metadata and graph-write proposals
- `ClaimCurationHarness`
  curation-shaped with governed mutation tools
- `GraphOpsHarness`
  action or review-shaped with admin-grade tools

#### 3. `SupervisorHarness` For End-To-End Program Composition

Use this only where the full cycle needs composition.

Example:

- supervisor starts a bootstrap child harness
- then a claim-review child harness
- then a summarization child harness

This matches the Artana docs well:

- specialized child harnesses keep smaller tool surfaces
- the supervisor creates the end-to-end product flow without collapsing
  everything into one giant prompt

#### 4. `ContextBuilder` And Workspace Snapshots For Research-Space Memory

Artana docs support:

- `ContextBuilder(workspace_context_path=...)`
- workspace snapshot helpers
- artifact helpers

This is how to implement the harness-engineering idea of structured model
memory.

For each research space, the harness should inject:

- current research objective
- graph summary
- open questions
- latest run summary
- latest chat summary
- schedule intent
- operating policies

Recommended memory split:

- graph facts and claims in `artana_evidence_db`
- research-space workspace snapshot in Artana harness state
- longer summaries and plans as artifacts

#### 5. Artifacts As Durable Research Memory

Artana artifacts are first-class and persisted as run summaries.

Use artifacts for:

- research brief
- run delta report
- chat summary
- candidate claim pack
- evidence bundle
- next-question backlog
- schedule cycle summary

This is likely the right place to store the evolving non-graph memory that the
agent needs between runs.

#### 6. `AcceptanceSpec` And Verify Loops For Research Quality Gates

The docs provide:

- `run_draft_model(...)`
- `run_verify_model(...)`
- `AcceptanceSpec`
- `ToolGate`

That is directly useful here.

Examples:

- do not finalize a research answer unless `graph.search` and evidence-grounding
  gates pass
- do not finalize a graph-write proposal unless duplication and policy checks
  pass
- do not mark a continuous-learning cycle complete unless a delta artifact was
  produced

This is one of the strongest Artana features for this design because it turns
"answer quality" into explicit completion criteria.

#### 7. `KernelPolicy.enforced_v2()` For Governed Writes

The docs are explicit:

- `enforced_v2` requires safety middleware
- side-effect tools can require intent, semantic idempotency, limits,
  approvals, and invariants

This fits the graph-write model exactly.

Use read tools with low friction.
Use mutating tools with:

- typed intent plan
- semantic idempotency
- capability requirement
- approval gate
- deterministic invariants

This is how graph mutation stays governed even when the agent is autonomous.

#### 8. Kernel Leases And Status APIs For Scheduler/Worker Integration

The Artana docs do support worker-facing orchestration contracts:

- `get_run_status`
- `get_run_progress`
- `resume_point`
- `list_active_runs`
- `acquire_run_lease`
- `renew_run_lease`
- `release_run_lease`

The docs also explicitly show:

- worker loops
- durable restart behavior
- external scheduler integration

This is the correct way to implement recurring research.

Important design conclusion:

- Artana is orchestration-agnostic
- it supports scheduler and worker patterns well
- but the recurring schedule trigger itself should be an external scheduler or a
  thin scheduling service layer

So the right architecture is:

- schedule definition stored by `artana_evidence_api`
- external scheduler or internal scheduler loop enqueues run ids
- Artana workers lease and execute those runs durably

### Concrete Artana Runtime Topology

```text
Research UI / API
-> artana_evidence_api
-> create run record + Artana run_id
-> scheduler enqueues or triggers run
-> worker acquires Artana run lease
-> specialized harness executes
-> harness calls graph and research tools
-> artifacts / workspace snapshots / outcomes persisted in Artana
-> approvals pause run when needed
-> resumed worker continues same run
```

### Concrete Harness Mapping

#### `ResearchBootstrapHarness`

Artana pieces:

- `StrongModelAgentHarness`
- research-shaped context builder
- tools for query generation, PubMed search, enrichment, extraction, graph
  write proposal
- acceptance gates for evidence grounding and artifact creation

Outputs:

- research brief artifact
- source inventory artifact
- candidate claim pack artifact
- graph write proposals

#### `GraphChatHarness`

Artana pieces:

- `StrongModelAgentHarness`
- workspace snapshot injection
- graph-read tools, artifact-read tools, optional fresh retrieval tools
- acceptance gates for grounded answer quality

Outputs:

- chat answer
- answer evidence bundle
- optional proposed graph updates
- updated chat summary artifact

#### `ContinuousLearningHarness`

Artana pieces:

- `StrongModelAgentHarness`
- schedule metadata in workspace state
- tools for graph read, literature refresh, comparison, and proposal generation
- verify loop that checks a delta artifact was produced

Outputs:

- cycle delta report
- newly found paper list
- candidate claims
- next-question backlog

#### `ClaimCurationHarness`

Artana pieces:

- `CurationHarness` or `StrongModelAgentHarness` with curation posture
- governed mutation tools under `enforced_v2`
- human approval path:
  approve -> resume -> retry

Outputs:

- review packet
- approved or rejected claim actions
- curation summary artifact

### Where Artana Fits Very Well

- durable long-running runs
- resumable chat or research workflows
- governed side-effect tools
- artifact-backed memory
- supervisor composition
- worker leasing and multi-worker recovery
- auditability through event ledger and summaries

### Where You Still Need To Build Product-Specific Layers

Artana docs do not replace these pieces. You still need:

- graph-specific tool adapters over `artana_evidence_db`
- PubMed and external-source tool adapters
- research-space registry and schedule definitions
- chat-session API layer
- UI for runs, approvals, artifacts, and schedules
- policy choices for what can auto-apply versus require human approval

### Best Practical Plan

If the goal is to achieve this with Artana, the strongest path is:

1. Build `artana_evidence_api` around `StrongModelAgentHarness`.
2. Create specialized harness templates instead of one giant harness.
3. Expose graph and research capabilities as typed Artana tools.
4. Use artifacts and workspace snapshots as durable research-space memory.
5. Put all mutating graph tools behind `KernelPolicy.enforced_v2()`.
6. Drive recurring runs through a scheduler plus Artana worker leases.
7. Use `SupervisorHarness` only for composed end-to-end programs.
