# User Guide

This guide is for a non-expert user.

You do not need to know what a graph database is, how Artana works, or how the
AI runtime is wired internally.

The goal of this guide is simple:

- help you understand what this service is for
- show the safest beginner workflow first
- then show the bigger and more advanced workflows when you are ready

If you only read one section, read
[The Safest Beginner Workflow](#the-safest-beginner-workflow).

## What This Service Does

In plain English, `artana_evidence_api` is a research assistant with memory,
review steps, and traceability.

It helps you:

- collect research evidence from text notes, PDFs, and searches
- ask AI to extract possible facts from that evidence
- review those proposed facts before they become official
- ask grounded questions over your documents and graph
- run larger research jobs that can search, summarize, connect ideas, and stage
  reviewable outputs

The important part is this:

the service is not just a chatbot.

It is a governed workflow system. That means it tries to keep track of:

- where a claim came from
- what evidence supported it
- what the AI suggested
- what a human approved or rejected
- what happened during a task

## Data Sources: Not Just PubMed

One important correction:

this service is not PubMed-only.

PubMed is just the most visible source in the beginner examples because it is
the easiest general-purpose research example.

Today, the service works with a broader source set.

### Direct Researcher-Facing Sources

These are the sources a researcher can reach pretty directly through public
endpoints or obvious user flows:

- `text`: paste a note directly into the service
- `pdf`: upload a tracked PDF
- `pubmed`: run literature discovery searches
- `marrvel`: run gene-centered discovery searches

### Workflow-Managed Sources

These are sources the larger orchestration flows can use when enabled:

- `clinvar`
- `drugbank`
- `alphafold`
- `clinical_trials`
- `mgi`
- `zfin`
- `uniprot`
- `hgnc`
- `mondo`

In practice, these usually show up through larger workflows like
`research-plan`, bootstrap-style discovery, or guarded orchestration rather
than through the very first beginner examples.

### Why PubMed Shows Up More In The Docs

The beginner guide focused on the shortest safe flow:

1. add evidence
2. extract staged work
3. review the queue
4. ask grounded questions

PubMed fits neatly into that story because it is easy to explain as "search for
papers."

The docs were under-explaining the broader source surface, not reflecting the
full service accurately enough.

## The One-Minute Mental Model

Think of the service like this:

1. you give it research material
2. it creates a work session called a `task`
3. the AI reads, searches, or reasons inside that task
4. the service saves outputs, progress, and decisions
5. you review anything important before it becomes official

For beginners, the easiest version is even simpler:

1. add a document
2. extract staged work
3. review the queue
4. ask questions

That is the best first workflow because it is easy to understand and easy to
audit later.

## What This Service Is Not

It helps to know what this service is not.

It is not:

- your raw graph database
- a replacement for human judgment
- a promise that every AI answer is true
- a giant one-shot "do everything automatically" button

It sits on top of the graph service and orchestrates AI-assisted work around
that graph.

If you want the simplest boundary:

- `artana_evidence_db` owns official graph state and graph governance
- `artana_evidence_api` owns AI-assisted workflows, tasks, chat, extraction,
  orchestration, review, and transparency

## Who This Guide Is For

This guide is a good fit if you are:

- a researcher
- a curator
- a product person testing the system
- a domain expert who wants to review evidence without learning the whole codebase
- a developer who wants the product-level picture before reading the API reference

## Before You Start: Get An API Key

To use the real service features in this guide, you normally need your own
Artana API key.

This is the main credential used by normal requests:

```bash
-H "X-Artana-Key: $ARTANA_API_KEY"
```

In simple terms:

- `ARTANA_API_KEY` is your normal personal key for everyday API calls
- `ARTANA_EVIDENCE_API_BOOTSTRAP_KEY` is a one-time operator secret used only
  to create the first user and first API key on a fresh self-hosted deployment
- `Authorization: Bearer ...` also works in many places, but this guide uses
  `X-Artana-Key` because it is the simplest beginner path

One important non-expert note:

you do not normally generate or send the model-provider key yourself when using
this product.

For example, `OPENAI_API_KEY` is usually configured on the server side by the
operator. As a normal user, the key you usually need is your own
`ARTANA_API_KEY`.

### What You Need

For the examples in this guide, it helps to set:

```bash
export HARNESS_URL="http://localhost:8091"
export ARTANA_API_KEY="art_sk_your_key"
export SPACE_ID="your-space-id"
```

If you do not have `ARTANA_API_KEY` yet, use one of the flows below.

If you are using an already-running shared deployment and you are not the
operator, the simplest path is usually:

- ask the admin or operator for an Artana API key
- or ask them to create one for your account through the normal API key routes

### Easiest First-Time Setup On A Fresh Self-Hosted Deployment

If this is the first user on a fresh deployment, ask the operator for the
bootstrap secret.

Then run:

```bash
export HARNESS_URL="http://localhost:8091"
export ARTANA_EVIDENCE_API_BOOTSTRAP_KEY="your-bootstrap-secret"

eval "$(
  venv/bin/python scripts/issue_artana_evidence_api_key.py \
    --base-url "$HARNESS_URL" \
    --bootstrap-key "$ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" \
    --email researcher@example.com \
    --username researcher \
    --full-name "Researcher Example"
)"
```

That helper script talks to the service and prints shell exports for you. By
default it sets:

- `ARTANA_API_BASE_URL`
- `ARTANA_API_KEY`
- `ARTANA_KEY_ID`
- `ARTANA_KEY_METHOD`
- `ARTANA_USER_EMAIL`
- sometimes `ARTANA_DEFAULT_SPACE_ID` and `ARTANA_DEFAULT_SPACE_SLUG`

If you prefer the raw API instead of the helper script, the first-key route is:

```bash
curl -s "$HARNESS_URL/v2/auth/bootstrap" \
  -X POST \
  -H "X-Artana-Bootstrap-Key: $ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "researcher@example.com",
    "username": "researcher",
    "full_name": "Researcher Example",
    "role": "researcher",
    "api_key_name": "Default CLI Key",
    "api_key_description": "Created from the user guide",
    "create_default_space": true
  }'
```

Important:

- this bootstrap flow is only for the first user on a fresh self-hosted setup
- once bootstrap has already happened, the service will reject another bootstrap
  attempt

### Easiest Way To Create Another API Key Later

If the deployment is already bootstrapped and you already have one working
credential, create another key with:

```bash
venv/bin/python scripts/issue_artana_evidence_api_key.py \
  --base-url "$HARNESS_URL" \
  --mode create \
  --api-key "$ARTANA_API_KEY" \
  --api-key-name "Laptop CLI Key"
```

You can also do that directly through HTTP:

```bash
curl -s "$HARNESS_URL/v2/auth/api-keys" \
  -X POST \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Laptop CLI Key",
    "description": "Extra key for local usage"
  }'
```

### Quick Check That Your Key Works

The easiest sanity check is:

```bash
curl -s "$HARNESS_URL/v2/auth/me" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

If that works, your key is valid and the service can resolve your identity.

### Get Or Reuse Your Default Space

If you do not already know your `SPACE_ID`, the easiest beginner setup call is:

```bash
curl -s "$HARNESS_URL/v2/spaces/default" \
  -X PUT \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

That returns your default space if it already exists, or creates it if it does
not.

For the rest of this guide, the examples assume:

```bash
export HARNESS_URL="http://localhost:8091"
export ARTANA_API_KEY="art_sk_your_key"
export SPACE_ID="your-space-id"
```

## The Main Things You Will Work With

You will see a few words again and again.

### Research Space

A `space` is your working area.

It keeps one project, team, or topic separated from another.

You can think of it as a folder plus permissions plus graph context.

### Document

A `document` is evidence you gave the system.

Examples:

- a text note
- a PDF
- a paper you want tracked

### Task

A `task` is one AI job or workflow execution.

Examples:

- extract facts from one document
- answer one grounded chat question
- bootstrap a research space
- run continuous learning

### Proposal

A `proposal` is a staged suggestion.

It is the system saying:

"I think this might be worth adding, but I want review before it becomes official."

### Review Item

A `review item` is the unified thing you actually review in the product.

It can represent:

- a proposal
- a review-only follow-up item
- a paused approval from a task

That is why review items are now the easiest default review surface.

### Approval

An `approval` is a human yes/no decision on something the system paused for.

### Output

An `output` is saved content from a task.

Examples:

- summaries
- candidate claims
- graph snapshots
- transparency records

### Progress And Events

These are the "what is happening right now?" views for a task.

- `progress` is the latest status snapshot
- `events` are the step-by-step history

## The Safest Beginner Workflow

If you are new, start here.

This is the best path because it teaches the product without hiding how the
system thinks.

### Step 1: Add One Document

Start with one note or one PDF.

Text note:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/text" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 evidence note",
    "text": "MED13 associates with cardiomyopathy.",
    "metadata": {}
  }'
```

PDF:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/pdf" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -F "file=@./paper.pdf" \
  -F "title=MED13 paper"
```

What you are doing:

- creating a tracked evidence object
- giving the system something concrete to reason from

What success looks like:

- you get back a `document_id`

### Step 2: Extract Staged Work

Now ask the system to read the document and stage reviewable findings.

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/<document_id>/extraction" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -X POST
```

What the system does:

- reads the source
- extracts candidate facts
- stores promotable facts as `pending_review` proposals
- stores review-only follow-up items when something still needs a human decision

For ordinary documents, those proposals may look like reviewed claims.

For genomics-capable documents, the extraction path is more structured. The
system can stage:

- one `entity_candidate` for a variant such as `MED13 c.977C>A`
- `observation_candidate` proposals for things like transcript, classification,
  zygosity, inheritance, exon, or coordinates
- `candidate_claim` proposals for variant-rooted phenotype or mechanism claims
- explicit review items when the variant is incomplete or a phenotype still
  needs synthesis

That means a messy clinical genetics note is no longer forced into the older
"generic relation only" shape.

What success looks like:

- you get a result with a `proposal_count`
- you may also get a `review_item_count`
- genomics documents can also mark the document as `variant_aware_extraction`
  in metadata
- if you retry after a partial earlier extraction attempt, the service now reuses matching
  already-staged proposals and review items instead of returning a misleading
  empty extraction result

### Step 3: Review The Queue

List the unified queue:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items?document_id=<document_id>" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

This queue can include:

- proposals you can `promote` or `reject`
- review-only items you can `convert_to_proposal`, `mark_resolved`, or `dismiss`
- approvals from paused tasks that you can `approve` or `reject`

One important nuance:

- promoting an `observation_candidate` expects the subject entity to already
  exist in the graph
- if the observation refers to a new variant or other new entity, promote that
  entity candidate first, then retry the observation

If you want the lower-level proposal records directly, you can still list them:

List proposals:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/proposed-updates?document_id=<document_id>" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Promote one:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "promote",
    "reason": "Reviewed and approved",
    "metadata": {}
  }'
```

Reject one:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reject",
    "reason": "Not strong enough",
    "metadata": {}
  }'
```

What this means in simple words:

- `promote` means "yes, this can count as official staged knowledge"
- `reject` means "no, keep this out"
- `convert_to_proposal` means "this review note is now concrete enough to become a real proposal"
- `mark_resolved` means "I handled this review-only follow-up"
- `dismiss` means "do not keep asking me about this one"

Compatibility note:

- `resolve` still works as an older alias for `mark_resolved`, but new clients
  should send `mark_resolved`.

### Step 4: Ask A Grounded Question

Create a chat session:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/chat-sessions" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "First research chat"
  }'
```

Ask a question:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/chat-sessions/<session_id>/messages" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What does this document suggest about MED13?",
    "document_ids": ["<document_id>"],
    "refresh_pubmed_if_needed": true
  }'
```

What to look for in the response:

- the answer itself
- verification status
- evidence or evidence chains
- fresh literature hints when enabled

That is the core user journey.

If you understand that flow, you understand the product.

## A Simpler Way To Choose What To Do

If you are unsure which feature to use, use this table.

| Your goal | Start with | Why |
| --- | --- | --- |
| Review one note or paper | Documents + extraction + review items | Safest and easiest workflow |
| Ask questions about a known document set | Chat sessions | Keeps answers tied to documents and graph context |
| Find literature first | PubMed search | Good before extraction or bootstrap |
| Build an initial project map | Research bootstrap | Bigger starting workflow for a new space |
| Keep a topic refreshed over time | Continuous learning | Re-runs research on a schedule |
| Compare many generated ideas | Mechanism discovery | Produces ranked hypothesis-style outputs |
| Force approval checkpoints into claim writing | Claim curation | Most governed path for graph-impacting claims |
| Run a bigger orchestrated sequence | Supervisor | Composes several workflows into one parent task |

## How A Researcher Can Actually Use The Different Sources

This is the practical version.

Instead of asking "what sources exist?", ask:

- am I bringing my own evidence?
- am I discovering external evidence?
- am I asking the service to do a bigger multi-source sweep?

### 1. Bring Your Own Evidence

Use this when you already have material in hand.

Sources:

- `text`
- `pdf`

Best for:

- private notes
- paper excerpts
- manually selected PDFs
- controlled review of one specific source

Typical workflow:

1. submit text or upload PDF
2. run extraction
3. review the queue
4. ask grounded questions

This is still the best place for a new researcher to begin.

### 2. Search External Literature Directly

Use this when you want discovery before review.

Sources:

- `pubmed`
- `marrvel`

Best for:

- finding papers
- exploring gene-centered background
- pulling in outside evidence before you commit to a direction

#### PubMed

Use PubMed when your question is mostly:

- what papers exist?
- what does the literature say?
- what should I read next?

Typical path:

1. run a PubMed search
2. inspect the returned job
3. optionally ingest or follow up with document-centered review
4. use the results to seed chat, bootstrap, or research-plan work

#### MARRVEL

Use MARRVEL when your question is more gene-centric and you want structured
cross-resource context around a gene or variant.

Typical path:

1. run a MARRVEL search for a gene symbol or variant
2. inspect the result and available panels
3. use that output as supporting context for later extraction, graph review, or
   broader research workflows

Important nuance:

the direct MARRVEL search endpoints are real researcher-facing entry points,
but the older direct "seed graph entities immediately from MARRVEL" style is no
longer the main pattern. The healthier pattern is to let MARRVEL-derived
material flow through the same governed document/proposal pipeline as other
evidence.

The direct ingest route still exists for advanced or system-owned usage:

- `POST /v2/spaces/{space_id}/sources/marrvel/ingestion`

### 3. Ask For A Bigger Multi-Source Research Sweep

Use this when your question is larger than one document or one search.

Best entry point:

- `research-plan`

This is where the service can combine multiple enabled source families in one
task.

The public request shape supports a `sources` map, for example:

```json
{
  "objective": "Understand MED13 mechanisms and translational evidence",
  "seed_terms": ["MED13", "cardiomyopathy"],
  "sources": {
    "pubmed": true,
    "marrvel": true,
    "clinvar": true,
    "drugbank": false,
    "alphafold": false,
    "clinical_trials": false,
    "mgi": false,
    "zfin": false
  }
}
```

In simple terms:

- turn `true` on for the source families you want included
- leave `false` for the ones you do not want right now

Good rule of thumb:

- start with `pubmed + marrvel + clinvar`
- add `drugbank` when therapy or target questions matter
- add `clinical_trials` when translational or trial evidence matters
- add `mgi` or `zfin` when model-organism evidence matters
- add `alphafold` when structure or protein-shape context matters

### 4. Use Bootstrap For A First Map, Then Graduate To Research-Plan

Bootstrap is still useful, but it is a narrower mental model.

If what you want is:

- "give me a first picture of this topic"

bootstrap is fine.

If what you want is:

- "use several sources intentionally and let me choose them"

`research-plan` is the better fit.

### 5. Use Chat After You Have Evidence In Place

Chat works best after at least one of these is true:

- you uploaded documents
- you ran literature discovery
- you completed a broader multi-source task

That way the chat is grounded in something real instead of being asked to think
from scratch.

## A Simple Source Selection Strategy

If you are a researcher and do not want to overthink this, use:

### Small Question

- `text` or `pdf`
- then chat

### Literature Question

- `pubmed`
- then documents or chat

### Gene-Centered Discovery Question

- `marrvel`
- optionally `clinvar`
- then chat or research-plan

### Broad Mechanism Or Evidence-Mapping Question

- `research-plan`
- enable `pubmed`, `marrvel`, and `clinvar`
- add `drugbank`, `clinical_trials`, `mgi`, `zfin`, or `alphafold` only when
  the question needs them

This keeps the workflow understandable.

## What To Use First, Second, And Later

Good learning order:

1. documents
2. proposals
3. chat
4. PubMed search
5. bootstrap
6. claim curation
7. supervisor
8. schedules and continuous learning

This order works because each step builds on the last one.

## The Next Level: Understanding Tasks

Once you move beyond one document, you need to understand `tasks`.

A task is the service's way of making AI work inspectable.

That matters because bigger workflows are not just one response body. They
have:

- status
- progress
- events
- outputs
- pause/resume behavior

### Why Runs Matter

Without tasks, a long AI workflow would feel like a black box.

With tasks, you can answer:

- is it still working?
- what step is it on?
- did it pause for review?
- what did it produce?

### The Main Run Endpoints

| What you want to know | Endpoint |
| --- | --- |
| Is the task alive? | `GET /v2/spaces/{space_id}/tasks/{task_id}` |
| What is it doing now? | `GET /v2/spaces/{space_id}/tasks/{task_id}/progress` |
| What happened step by step? | `GET /v2/spaces/{space_id}/tasks/{task_id}/events` |
| What files or outputs did it save? | `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs` |
| What tools was it allowed to use? | `GET /v2/spaces/{space_id}/tasks/{task_id}/capabilities` |
| What did it actually decide to do? | `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions` |
| It paused, now what? | `POST /v2/spaces/{space_id}/tasks/{task_id}/resume` |

### A Good Beginner Habit

When something feels confusing, inspect the task in this order:

1. task
2. progress
3. events
4. outputs
5. capabilities
6. decisions

That usually tells the story.

## Chat: When To Trust It, And When To Slow Down

Chat is useful, but it works best when you treat it as grounded analysis, not
magic.

Use chat when:

- you want a summarized answer
- you want the system to combine graph context and documents
- you want cited or traceable reasoning

Slow down and review more carefully when:

- the answer would change official graph state
- the evidence is weak or mixed
- the language in the answer sounds more certain than the evidence really is

The default healthy pattern is:

1. ask the question
2. inspect verification and evidence
3. stage proposals if needed
4. review before promoting

## PubMed Search: Best For "What Is Out There?"

Use PubMed search when the main problem is discovery, not graph writing.

This is good for:

- finding papers on a topic
- checking whether the system is missing recent literature
- seeding later workflows

Start a search:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/sources/pubmed/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "gene_symbol": "MED13",
      "search_term": "MED13 cardiomyopathy",
      "max_results": 25
    }
  }'
```

This is often the right move before a bootstrap task or before asking a broad
chat question.

## MARRVEL Search: Best For Gene-Centered Discovery

Use MARRVEL when the main problem is:

- gene-centered background discovery
- quick cross-panel context
- disease and variant context around a gene

Typical use:

1. search by gene symbol or variant
2. inspect the returned panels
3. use the result to guide later extraction, review, or multi-source tasks

This is especially useful when a researcher starts with a gene and wants a fast
structured view before doing broader workflow orchestration.

## Bootstrap: Best For Starting A New Space

Use research bootstrap when you want the system to help create an initial map
of a topic.

In simple terms, bootstrap tries to give you a head start.

It can:

- search for initial evidence
- gather context around seed entities
- create a first research brief
- stage initial graph-write proposals for review

Good time to use it:

- you just created a new research space
- you have one or a few seed entities
- you want the system to do more than one tiny step

Not the best time to use it:

- you only want to review one known paper
- you are still learning the basic document workflow

## Claim Curation: Best For High-Governance Writes

This is the workflow to use when you care a lot about controlled promotion of
claims.

Use it when:

- the write matters
- duplicate/conflict checking matters
- you want explicit approval behavior

This workflow is more formal than casual chat or document extraction.

It is the "let's be careful here" mode.

## Supervisor: Best For Multi-Step Guided Work

Supervisor is the bigger orchestrator.

It can combine workflows such as:

- bootstrap
- briefing chat
- claim curation

This is useful when you want one parent workflow that coordinates several
child workflows while preserving review and traceability.

If you are new, do not start here.

Learn documents, proposals, and chat first.

Supervisor becomes much easier once those make sense.

## Continuous Learning: Best For Ongoing Monitoring

Continuous learning is for repeated refreshes over time.

Use it when you want the service to keep checking a topic, collect deltas, and
surface what changed.

This is useful for:

- active research programs
- topics with new literature arriving frequently
- recurring monitoring of a disease, gene, mechanism, or evidence area

This is usually a second-stage feature, not a day-one feature.

## Mechanism Discovery: Best For Ranked Idea Generation

Mechanism discovery is the more exploratory mode.

It is helpful when you want the system to produce and rank mechanism-like
candidates or hypothesis-style outputs for review.

This is powerful, but it is not the place to begin if your first goal is
simply "put one paper in and review the facts."

## Transparency: How To See What The AI Was Allowed To Do

One of the best things about this service is that you can inspect what
happened.

Two endpoints matter a lot:

- `GET /capabilities`
- `GET /decisions`

In plain English:

- `capabilities` says what the task could use
- `decisions` says what the task actually did

This matters when someone asks:

- why did the AI not use a tool?
- why did it pause?
- why was something reviewed manually?
- what was allowed versus what really happened?

That is one of the main differences between a governed workflow system and a
plain chatbot.

## What A Healthy Beginner Session Looks Like

A healthy beginner session often looks like this:

1. create or choose a research space
2. add one document
3. extract staged work
4. review the queue
5. open a chat session
6. ask a grounded question
7. inspect verification
8. only then move into larger workflows

If you do that a few times, the bigger features become much less intimidating.

## Common Mistakes To Avoid

### Mistake 1: Starting With The Biggest Workflow

Do not start with supervisor if you have never reviewed one document.

Start small first.

### Mistake 2: Treating Chat As Official Truth

Chat answers are useful, but official graph-impacting changes should still go
through the review path.

### Mistake 3: Ignoring Verification And Evidence

A readable answer is not the same thing as a well-grounded answer.

Always inspect:

- verification status
- evidence
- proposals
- approval requirements

### Mistake 4: Skipping Run Inspection

When a long workflow feels confusing, people sometimes retry immediately.

Usually it is better to inspect:

- progress
- events
- outputs

first.

### Mistake 5: Mixing Discovery With Approval

PubMed search, chat, bootstrap, and mechanism discovery are great for
exploration.

Proposal promotion and claim curation are for governed acceptance.

Those are related, but they are not the same thing.

## A Friendly "Which Endpoint Family Do I Need?" Cheat Sheet

| If you want to... | Use... |
| --- | --- |
| check the service is alive | `/health` |
| see what workflows exist | `/v2/workflow-templates` |
| upload evidence | `/documents/text` or `/documents/pdf` |
| extract findings from a document | `/documents/{document_id}/extraction` |
| review staged findings | `/review-items` |
| ask grounded questions | `/chat-sessions` and `/messages` |
| stage graph writes from verified chat | `/chat-sessions/{session_id}/suggested-updates` |
| inspect long-running work | `/tasks`, `/progress`, `/events`, `/outputs` |
| inspect AI policy and tool visibility | `/capabilities` and `/decisions` |
| search literature | `/sources/pubmed/searches` |
| start a larger research job | workflow-specific task endpoints |
| resume a paused governed workflow | `/tasks/{task_id}/resume` |

## Recommended Learning Path For Teams

If you are onboarding a team, this order works well:

### Day 1

- health
- one text document
- extraction
- review items

### Day 2

- chat with document context
- task inspection
- transparency inspection

### Day 3

- PubMed search
- bootstrap

### Day 4 And Later

- claim curation
- supervisor
- continuous learning
- mechanism discovery

This keeps the learning curve gentle.

## How To Think About Safety

The service is trying to balance usefulness with control.

A good practical rule is:

- let AI read, summarize, search, and suggest
- let governed review decide what becomes official

That is why proposals, approvals, tasks, and transparency exist.

## When You Are Ready For More Detail

After this guide, read the docs in this order:

1. [Getting Started](./getting-started.md)
2. [Full Research Workflow](./full-research-workflow.md)
3. [Core Concepts](./concepts.md)
4. [Example Use Cases](./use-cases.md)
5. [Run Transparency](./transparency.md)
6. [API Reference](./api-reference.md)

## Final Advice

If you are unsure what to do next, return to the default path:

1. add evidence
2. extract staged work
3. review the queue
4. ask grounded questions

That path teaches the product better than any diagram.
