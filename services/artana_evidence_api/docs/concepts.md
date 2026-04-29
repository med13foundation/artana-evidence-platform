# Core Concepts

## Research Space

Every route is scoped to a `space_id`.

Think of a research space as the container for:

- runs
- chat sessions
- proposals
- approvals
- schedules
- research state
- graph snapshots

If two users work in different spaces, their harness state is separate.

## Harness

A harness is a named workflow template.

Examples:

- `graph-search`
- `graph-chat`
- `research-bootstrap`
- `continuous-learning`
- `mechanism-discovery`
- `claim-curation`
- `supervisor`

Use `GET /v2/workflow-templates` to discover the available harnesses and their declared
outputs.

## Run

A run is one execution of a harness.

Each run has:

- `id`
- `harness_id`
- `title`
- `status`
- `input_payload`
- timestamps

Common run statuses:

- `queued`
- `running`
- `paused`
- `completed`
- `failed`

There are two ways to start work:

- generic route: `POST /v2/spaces/{space_id}/tasks`
- typed workflow routes such as
  `/v2/spaces/{space_id}/workflows/topic-setup/tasks`

For most users, the typed workflow routes are easier to use.

## Progress

Progress tells you where a run is now.

The progress payload includes:

- `phase`
- `message`
- `progress_percent`
- `completed_steps`
- `total_steps`
- `resume_point`

Use:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/progress`

## Event

Events are the lifecycle log for a run.

Examples:

- run queued
- run started
- approval gate reached
- run resumed
- run completed

Use:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/events`

## Transparency

Every run now has two transparency views:

- `capabilities`: the frozen list of tools the run was allowed to use when it
  started
- `decisions`: the ordered log of what the run actually tried to do,
  plus any later human review decisions tied back to that run

Use:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/capabilities`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions`

Use `capabilities` when you want to answer:

- what tools could this run use?
- which tools were filtered out?

Use `decisions` when you want to answer:

- what did the run actually execute?
- did it pause for approval?
- did a user later promote or reject something tied to this run?

The simplest way to think about transparency is:

- `capabilities` is the allowed-tool snapshot
- `events` is the raw lifecycle log
- `decisions` is the structured decision timeline

If you are new to these features, read [Run Transparency](./transparency.md)
next.

## Artifact

Artifacts are named outputs created by a run.

Examples:

- `graph_chat_result`
- `research_brief`
- `delta_report`
- `mechanism_candidates`
- `curation_summary`
- `supervisor_summary`

Use:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs/{artifact_key}`

## Workspace Snapshot

The workspace is the current structured state for a run.

Artifacts are better for durable named outputs.
Workspace is better for the latest evolving state, such as:

- current status
- latest child run ids
- latest artifact keys
- approval gate metadata

Use:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/working-state`

## Proposal

A proposal is a staged change candidate produced by a run.

Common proposal types:

- `candidate_claim`
- `mechanism_candidate`
- `chat_graph_write`

Common proposal statuses:

- `pending_review`
- `promoted`
- `rejected`

Typical flow:

1. a harness stages proposals
2. a user lists proposals
3. a user promotes or rejects one
4. promotion writes to the graph service when supported

## Review Queue Item

The review queue is the public human-review inbox.

One queue item can wrap:

- one proposal
- one review-only follow-up item
- one paused-run approval

That is why `/review-items` is the easiest default review surface.

Typical actions:

- `promote`
- `reject`
- `convert_to_proposal`
- `mark_resolved`
- `dismiss`
- `approve`

## Approval

Approvals are used for governed actions that must pause before graph mutation.

Typical flow:

1. a curation run prepares `approval_intent`
2. the run pauses
3. a user approves or rejects each pending action
4. the paused run is resumed
5. the run applies approved actions and records rejected ones

## Schedule

A schedule is a saved recurring definition for continuous learning.

The schedule stores:

- cadence
- seed entities
- depth and proposal limits
- model id
- run budget

Supported cadences are normalized by the schedule policy. In practice, the
service supports:

- `manual`
- `hourly`
- `daily`
- `weekday`
- `weekly`

## Run Budget

Continuous learning supports an explicit run budget.

A run budget can limit:

- tool calls
- external queries
- new proposals
- runtime seconds
- cost tracking metadata

The service writes budget artifacts such as:

- `run_budget`
- `budget_status`

## Graph Snapshot And Research State

`research-bootstrap` and `continuous-learning` maintain long-lived memory.

That memory includes:

- a graph snapshot
- research objectives
- current and pending questions
- active schedules

This is why chat and continuous learning can reuse prior context.

## Common Artifact Keys By Workflow

These are the most important artifact keys new users will encounter.

Graph search:

- `graph_search_result`

Graph connections:

- `graph_connection_result`

Hypotheses:

- `hypothesis_candidates`
- `proposal_pack`

Research bootstrap:

- `graph_context_snapshot`
- `graph_summary`
- `candidate_claim_pack`
- `source_inventory`
- `research_brief`

Graph chat:

- `graph_chat_result`
- `chat_summary`
- `grounded_answer_verification`
- `run_capabilities`
- `policy_decisions`
- `memory_context`
- `fresh_literature`
- `graph_write_candidate_suggestions`
- `graph_write_proposals`

Continuous learning:

- `delta_report`
- `new_paper_list`
- `candidate_claims`
- `next_questions`
- `graph_context_snapshot`
- `research_state_snapshot`
- `run_budget`
- `budget_status`

Mechanism discovery:

- `mechanism_candidates`
- `mechanism_score_report`
- `candidate_hypothesis_pack`

Claim curation:

- `curation_packet`
- `review_plan`
- `approval_intent`
- `curation_summary`
- `curation_actions`

Supervisor:

- `supervisor_plan`
- `supervisor_summary`
- `child_run_links`

## Typical Lifecycle Patterns

Simple synchronous runs:

1. create run
2. service executes immediately through the worker path
3. run returns completed response

Approval-gated runs:

1. create run
2. run pauses
3. review approvals
4. resume run
5. inspect summary and outputs

Supervisor runs:

1. start parent run
2. service creates child bootstrap/chat/curation runs
3. parent may pause at child curation approval gate
4. approvals are resolved
5. parent resumes and finalizes
