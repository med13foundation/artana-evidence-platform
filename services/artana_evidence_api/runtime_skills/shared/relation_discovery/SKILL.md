---
name: graph_harness.relation_discovery
version: 1.0.0
summary: Scout dictionary-constrained relation candidates before synthesizing new graph connections.
tools:
  - suggest_relations
---
Use relation suggestion to scout a bounded candidate set from the current seed entities.

Treat suggestions as candidate inputs, not as accepted conclusions.
Keep only relations that remain coherent with the graph context, the source type, and the
user's requested relation filters.

When confidence is weak or the relation semantics are ambiguous, reject the candidate and
explain why instead of overcommitting.
