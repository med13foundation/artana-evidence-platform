---
name: graph_harness.graph_grounding
version: 1.0.0
summary: Ground answers and candidate discovery in current graph evidence before drafting conclusions.
tools:
  - get_graph_document
  - list_graph_claims
  - list_graph_hypotheses
---
Read the graph before reasoning.

Start by fetching the current graph shape for the active research space and seed context.
Use claim and hypothesis listings to verify whether the graph already contains support,
contradictions, or open exploratory threads relevant to the request.

Stay grounded in returned IDs, counts, and evidence references.
Do not invent provenance, claim IDs, hypothesis IDs, or relation details.

If the graph does not support a strong answer yet, say so clearly and downgrade the decision.
