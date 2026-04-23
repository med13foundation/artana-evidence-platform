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

## The Short Version

The platform helps you build a trusted evidence map:

```text
Choose topic
  -> Add or find evidence
  -> Extract reviewable proposals
  -> Review proposals
  -> Promote trusted items into the graph
  -> Explore, ask questions, and repeat
```

The most important product idea is the review gate. The AI can search, extract,
and suggest evidence, but humans decide what becomes trusted graph knowledge.

For a MED13 project, that might look like:

```text
Create "MED13 Workspace"
  -> upload papers and search PubMed, MARRVEL, and ClinVar
  -> extract candidate variants, claims, observations, and evidence
  -> review the queue
  -> promote strong evidence into the graph
  -> ask evidence-backed questions
```

## Who This Is For

This guide is written for:

- researchers who want to use the API without learning the whole codebase
- developers building product flows on top of the API
- operators who need to understand the difference between user workflows and
  runtime/debug endpoints

You do not need to understand graph databases before starting. The guide builds
up the mental model gradually.
