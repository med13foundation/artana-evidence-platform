# Artana Evidence Platform User Guide

Welcome. This guide explains how to use the Artana Evidence Platform as a
research evidence workspace, starting from setup and moving toward more
advanced workflows.

If you are new, read these in order:

1. [Getting Started](./01-getting-started.md)
2. [Core Concepts](./02-core-concepts.md)
3. [Workflow Overview](./03-workflow-overview.md)
4. [Adding Evidence](./04-adding-evidence.md)
5. [Reviewing And Promoting Evidence](./05-reviewing-and-promoting.md)
6. [Exploring The Graph And Asking Questions](./06-exploring-and-asking.md)
7. [Multi-Source And Automated Workflows](./07-multi-source-and-automation.md)
8. [Runtime, Debugging, And Transparency](./08-runtime-debugging-and-transparency.md)
9. [Endpoint Index](./09-endpoint-index.md)
10. [Real Use Cases](./10-real-use-cases.md)

## The Short Version

The platform helps you build a trusted evidence map:

```text
Choose topic
  -> Start an evidence run
  -> Let the harness search, select useful source records, and stage reviewable work
  -> Review proposals
  -> Promote trusted items into the graph
  -> Add follow-up ideas and repeat
```

The most important product idea is the review gate. The AI can search, extract,
and suggest evidence, but humans decide what becomes trusted graph knowledge.

For a MED13 project, that might look like:

```text
Create "MED13 Workspace"
  -> start an evidence run with a MED13 goal
  -> search PubMed, MARRVEL, ClinVar, or other supported source results
  -> create source handoffs and reviewable proposals/items for selected records
  -> review the queue
  -> promote strong evidence into the graph
  -> add a follow-up question and keep building the same space
```

## Who This Is For

This guide is written for:

- researchers who want to use the API without learning the whole codebase
- developers building product flows on top of the API
- operators who need to understand the difference between user workflows and
  runtime/debug endpoints

You do not need to understand graph databases before starting. The guide builds
up the mental model gradually.
