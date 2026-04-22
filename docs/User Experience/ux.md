# Research Inbox UX

## Purpose

This document describes the intended user experience for the MED13 research
inbox and graph harness services.

The goal is simple:

- a precision medicine researcher should be able to state a goal once
- connect the systems and evidence sources they already use
- receive a clear plan
- let the system run long-lived research work in the background
- stay in control of important decisions without becoming the AI's data-entry
  clerk

This UX is grounded in the current product concepts already present in the
codebase:

- `research space`
- `thread`
- `run`
- `artifact`
- `proposal`
- `approval`
- `schedule`
- `research state`
- `graph snapshot`

## Product Positioning

The product is not another ELN, LIMS, or clinical data warehouse.

It is the orchestration layer for precision medicine research.

Existing external systems remain the systems of record:

- ELNs
- LIMS
- clinical systems
- knowledge bases
- literature sources
- internal document repositories

The platform uses connectors to talk to those systems. Researchers should not
have to duplicate the same context into a second destination product just to
start working. A `research space` is therefore not a replacement notebook. It
is a bounded execution context for:

- objectives
- connected sources
- inbox threads
- agent runs
- schedules
- approvals
- artifacts
- durable research memory

## Design Principles

### 1. Inbox-first, not dashboard-first

The main human experience should feel like an inbox, not a control room. A
researcher should understand what is happening, what is needed from them, and
what changed since the last update without navigating a maze of screens.

### 2. System of orchestration, not system of record

The product should orchestrate work across connected systems. It should not ask
users to re-enter data that already exists elsewhere.

### 3. Scientific review, not graph maintenance

Researchers should review scientific claims, hypotheses, evidence deltas, and
recommended experiments. They should not be asked to think in graph nodes,
edges, or ontology bookkeeping.

### 4. Quiet by default

The system should not email or notify on every run. It should speak up only
when:

- it needs clarification
- a plan is ready
- a meaningful evidence change was found
- approval is required
- a digest is due

### 5. Curiosity with discipline

Curiosity is a feature, but it must be bounded. The system should explore
adjacent hypotheses and new evidence, but within explicit limits on:

- search scope
- runtime
- proposal volume
- review burden

### 6. Explain every recommendation

Every meaningful suggestion should carry:

- confidence
- rationale
- evidence
- provenance
- run history

### 7. Human control at the right moments

The system should be autonomous for search, synthesis, monitoring, and draft
planning. It should require human input when direction, interpretation, or
mutation risk becomes significant.

## Primary User

The primary user is a precision medicine researcher working on a focused
question such as:

- Which variants are most strongly associated with treatment response?
- What evidence supports a biomarker-defined patient subgroup?
- Which mechanisms could explain resistance in this disease setting?
- What should the team review next for a target, mutation, or cohort?

Secondary users may include:

- translational scientists
- bioinformaticians
- research leads
- clinical strategy teams
- curators or reviewers

## Core UX Objects

### Research space

The durable boundary for one research program. It contains:

- the objective
- configured connectors and sources
- team context
- inbox threads
- schedules
- run history
- research memory

### Thread

The canonical conversation surface between the researcher and the system. Email
is a transport for the thread, not a separate source of truth.

### Run

One execution of a harness workflow such as:

- `research-bootstrap`
- `graph-chat`
- `continuous-learning`
- `mechanism-discovery`
- `claim-curation`
- `supervisor`

### Artifact

Named output from a run, such as:

- `research_brief`
- `graph_summary`
- `source_inventory`
- `delta_report`
- `candidate_hypothesis_pack`
- `supervisor_plan`
- `supervisor_summary`

### Proposal

A reviewable scientific suggestion produced by a run, such as:

- candidate claim
- mechanism candidate
- chat-derived graph write

### Approval

A governed decision point for higher-risk actions.

### Research state

The durable memory for a research space, including:

- objective
- current hypotheses
- explored questions
- pending questions
- active schedules
- latest graph snapshot

## End-to-End Experience

### 1. Create research space

The researcher creates a research space from a lightweight intake flow.

The input should include:

- research title
- primary objective
- disease area or indication
- target, variant, biomarker, or patient subgroup of interest
- what success looks like
- key constraints
- preferred evidence sources
- connectors to existing external systems
- optional supporting documents

Important UX rule:

- the form should ask only for information the system cannot infer later
- external systems should be connected, not copied

On submission, the system should immediately:

- create the research space
- create an onboarding thread
- create an intake artifact
- ingest the attached documents or linked context
- inspect connected sources for obvious seed entities and context
- send the first researcher-facing email

### 2. First email: orient and clarify

The first email should be simple, human, and low jargon.

It should explain:

- what the system understood
- what it will do next
- what it needs clarified before activating the full workflow

The first email should usually ask three to five focused questions, for example:

- What would count as a useful first deliverable?
- Which evidence types matter most here?
- How aggressive should the system be in proposing new hypotheses?
- What should the system avoid spending time on?
- Which connected sources should be treated as authoritative?

The matching inbox thread should show:

- the original researcher intent
- the connected sources
- the current state summary
- the pending questions
- any attached supporting files

### 3. Researcher reply

The researcher replies in the same thread, by email or in the inbox UI.

The experience should feel conversational, but the system should translate the
reply into structured state:

- clarified objective
- success criteria
- evidence preferences
- excluded directions
- confidence thresholds
- review preferences

This step should also let the researcher add:

- more context
- more files
- new questions
- corrections to the system's understanding

### 4. AI writes the initial research plan

Once enough context is available, the system writes a concrete research plan.

The plan should not be generic. It should be operational.

It should include:

- the current research objective in plain language
- the main entities and subquestions the system will track
- the connected systems and evidence sources it will rely on
- the first exploration tracks
- the initial search and monitoring strategy
- the criteria for surfacing new evidence
- the criteria for proposing hypotheses
- the cadence for updates and digests
- the points that will require human review

The plan should be saved as an artifact and summarized into the inbox thread as
a readable message, not only as JSON.

### 5. Plan review and activation

The researcher reviews the plan in the inbox thread.

They should be able to:

- approve the plan
- request revisions
- narrow the scope
- increase or decrease autonomy
- change which sources are trusted

After approval, the research space becomes active.

The system then starts the appropriate background workflows, likely including:

- bootstrap
- schedule creation
- continuous learning
- mechanism discovery
- governed curation

### 6. Background research activity

Once active, the system should behave like a persistent research operator.

Its background work may include:

- refreshing literature and external evidence
- reading new source documents from connectors
- updating the structured evidence graph
- generating new candidate claims
- comparing new findings to prior state
- maintaining a backlog of next questions
- proposing mechanisms and experiments

This work should be largely invisible unless it produces something meaningful.

The researcher should not have to watch runs in real time.

### 7. Ongoing inbox experience

The inbox becomes the ongoing command center for the research space.

The thread list should help the researcher answer:

- What needs my attention now?
- What changed since I last looked?
- Which threads are blocked on me?
- Which threads are still running?

The thread detail experience should show:

- status
- next owner
- current summary
- timeline of messages and system updates
- linked artifacts
- linked evidence
- approvals and review items
- composer for follow-up instructions

### 8. Types of thread updates

Not every update should look the same. The system should generate distinct,
readable message types.

### Clarification request

Used when the system cannot proceed confidently.

### Plan draft

Used when the system proposes a concrete research program.

### Evidence update

Used when new evidence materially changes confidence, direction, or priority.

### Review recommendation

Used when the system has a ranked scientific suggestion that merits review.

### Approval request

Used when a higher-risk action needs an explicit decision.

### Digest

Used for regular summaries of progress, deltas, and next questions.

### Freeform researcher task

Used when the researcher asks the system to investigate something new inside the
same space.

### 9. Scientific review, not graph review

Review surfaces should be framed in the language of science, not data
structures.

Bad review prompt:

- Approve this edge between node A and node B.

Good review prompt:

- Review this candidate claim that Variant X may influence response to Drug Y.
- Review this hypothesis that Pathway Z may explain resistance in subgroup Q.
- Review this evidence delta showing two new papers that contradict the leading
  interpretation.

Every review card should show:

- the scientific claim or hypothesis
- why it is being surfaced now
- the evidence summary
- confidence and ranking
- what will happen if approved

### 10. Curiosity model

Curiosity is one of the product's differentiators, but it must be productive.

The system should maintain an explicit backlog of:

- active questions
- pending questions
- adjacent hypotheses
- proposed experiments
- contradictory evidence to resolve

Curiosity should be divided into two modes:

### Mission work

Directly tied to the approved research objective.

### Adjacent exploration

Potentially valuable ideas near the current objective, but not yet accepted as
part of the main plan.

The researcher should be able to control the desired level of curiosity:

- conservative
- balanced
- exploratory

### 11. Approval burden management

The system should be optimized to reduce review burden, not generate it.

That means:

- rank proposals before showing them
- cap proposal volume per run
- suppress low-confidence noise
- group similar suggestions
- learn from repeated rejects
- convert repeated preferences into policy

The scientist should not have to click "reject" all day.

### 12. User-initiated work after activation

At any time, the researcher should be able to send a new message such as:

- Find the strongest contradictory evidence to our current view.
- Reframe this question around pediatric patients only.
- Compare this target with the latest evidence from ClinVar and PubMed.
- Propose three experiments that would most reduce uncertainty.

The system should map that message onto:

- a new run
- a linked artifact
- optionally a new thread or subthread
- an updated research state if the request changes direction

### 13. Digests and notifications

The product should support scheduled and event-driven communication.

### Scheduled digest

For example:

- daily summary
- weekly precision medicine update
- morning review queue

### Event-driven message

For example:

- new biomarker evidence found
- leading hypothesis weakened
- review needed for a promoted claim
- connected source failed or became stale

Notification quality matters more than volume.

### 14. Connected-system experience

The system should treat connectors as first-class participants in the research
space.

A researcher should be able to see:

- which systems are connected
- which sources are active
- when they were last checked
- what kinds of evidence they contribute
- which sources are authoritative versus supplemental

The UX should make clear that the platform is reading from and acting through
connected systems, not asking the user to maintain duplicate truth.

### 15. Precision medicine framing

The experience should speak the language of precision medicine teams.

The system should consistently frame work around:

- targets
- variants
- biomarkers
- mechanisms
- patient subgroups
- treatment response
- resistance
- evidence quality
- clinical and translational relevance

It should avoid generic AI language where possible.

### 16. Example journey

1. A translational scientist creates a space for a resistant patient subgroup.
2. They connect literature and internal evidence sources and attach a strategy
   memo.
3. The system sends a first email explaining the next steps and asking four
   clarifying questions.
4. The scientist replies with the intended deliverable, evidence preferences,
   and the desired level of autonomy.
5. The system drafts a research plan with active questions, source priorities,
   schedules, and review policy.
6. The scientist approves the plan.
7. The system runs bootstrap, starts continuous monitoring, and begins
   mechanism discovery.
8. A day later, the scientist receives a digest saying two new papers reinforce
   one mechanism, one source contradicts it, and one candidate claim is worth
   review.
9. The scientist approves the claim, asks for stronger subgroup analysis, and
   requests two experiment ideas.
10. The system continues from that updated intent without the scientist having
    to restate the full context.

### 17. Success criteria for the UX

The UX is successful if a researcher can:

- start a meaningful research program in minutes
- stay mostly inside a thread-based experience
- understand what the system is doing without reading logs
- review only a small number of high-value decisions
- trust that connected systems remain the source of truth
- feel that the system is compounding knowledge over time

The UX is not successful if:

- the user must manually maintain graph structures
- the user is flooded with low-value alerts
- every autonomous run becomes a review burden
- the product requires copying data out of existing systems to get started
- the system feels like a stateless chatbot instead of a persistent research
  operator
