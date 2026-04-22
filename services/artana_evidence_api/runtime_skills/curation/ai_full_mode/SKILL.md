---
name: graph_harness.ai_full_mode
version: 1.0.0
summary: Submit AI Full Mode proposals and decision envelopes through the graph DB policy engine.
tools:
  - propose_graph_concept
  - propose_graph_change
  - submit_ai_full_mode_decision
  - propose_connector_metadata
---
Use this skill only when the workflow is explicitly allowed to use graph DB
AI Full Mode.

Proposal tools do not make official graph truth by themselves. They stage
candidate concepts, graph-change bundles, or connector metadata for graph DB
governance.

`submit_ai_full_mode_decision` may cause official changes only when the graph
DB space policy allows the AI principal, DB-computed confidence, risk tier, and
proposal snapshot hash. Always include concrete evidence, the exact proposal
hash the decision was based on, and a qualitative `confidence_assessment`.

Do not invent a numeric confidence score. The graph DB computes policy
confidence from `confidence_assessment`.

Do not bypass validation by writing official dictionary or graph state directly.
