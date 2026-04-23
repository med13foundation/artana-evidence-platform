# Artana Evidence API Docs

This folder contains the user-facing documentation for the
`artana_evidence_api` service.

The easiest mental model is:

1. add evidence
2. extract reviewable findings
3. review the queue
4. ask grounded questions

If you are brand new, learn that document-first flow before the larger harness
workflows.

If you are new to the service, read these files in order:

1. [User Guide](./user-guide.md)
2. [Getting Started](./getting-started.md)
3. [Full Research Workflow](./full-research-workflow.md)
4. [Core Concepts](./concepts.md)
5. [Example Use Cases](./use-cases.md)
6. [Run Transparency](./transparency.md)
7. [API Reference](./api-reference.md)

Useful companion files:

- Service overview: [README.md](../README.md)
- Interactive API docs when the service is running: `/docs`
- Raw OpenAPI spec: [openapi.json](../openapi.json)

If you only want the shortest path, read:

1. [User Guide](./user-guide.md)
2. [Getting Started](./getting-started.md)
3. [Full Research Workflow](./full-research-workflow.md)
4. [API Reference](./api-reference.md)

## Pick By Goal

Read:

- [User Guide](./user-guide.md) if you want the full non-expert explanation
  from beginner to advanced
- [Full Research Workflow](./full-research-workflow.md) if you want to review
  one PDF or text note and then ask questions about it
- [Example Use Cases](./use-cases.md) if you want concrete end-to-end examples
  for chat, PubMed, MARRVEL, bootstrap, schedules, or supervisor
- [Core Concepts](./concepts.md) if you want the vocabulary explained in plain
  English
- [Run Transparency](./transparency.md) if you want to inspect what a run could
  do versus what it actually did
- [API Reference](./api-reference.md) if you already know the workflow and just
  want route details

What this service does:

- Runs AI-assisted graph workflows such as search, chat, research bootstrap,
  continuous learning, mechanism discovery, claim curation, and supervisor
  orchestration.
- Works with direct evidence inputs such as text and PDFs, direct discovery
  sources such as PubMed and MARRVEL, and larger workflow-managed source
  families such as ClinVar, DrugBank, AlphaFold, ClinicalTrials, MGI, and
  ZFIN when enabled through broader orchestration flows.
- Stores run lifecycle state, artifacts, workspace snapshots, events, and
  progress through the Artana-backed runtime.
- Keeps domain state such as proposals, review-only queue items, approvals,
  schedules, research state, graph snapshots, and chat sessions.
- Exposes account, API-key, space-membership, graph-explorer, onboarding, and
  settings endpoints in addition to the main research workflow routes.
- Exposes an HTTP API that other services and UI clients can call directly.

Route execution model:

- Harness run-start routes are queue-first and worker-owned.
- The API creates a durable run record, seeds workspace state, and then either:
  - waits briefly for the worker so clients can keep the existing synchronous
    response shape, or
  - returns `202 Accepted` with run URLs when the caller sends
    `Prefer: respond-async` or the sync wait budget expires.
- This applies to chat, research bootstrap, research onboarding, graph search,
  graph connections, hypotheses, continuous learning, mechanism discovery,
  claim curation, supervisor, and research init.
- Worker concurrency is currently one run at a time per worker process.
  Horizontal scale comes from running more worker replicas against the same
  lease-backed queue.

What this docs set focuses on:

- a non-expert guide that starts simple and only gets more detailed when you
  are ready
- how to start the service
- how auth, API keys, and default spaces work
- how the document -> extract -> review queue -> chat workflow works
- what a run, document, proposal, review item, approval, and schedule mean
- when to use chat, documents, the review queue, proposals, graph explorer,
  PubMed, MARRVEL, onboarding, and research-init
- how to inspect run transparency through capabilities and policy decisions
- every available endpoint
- realistic beginner and advanced examples
