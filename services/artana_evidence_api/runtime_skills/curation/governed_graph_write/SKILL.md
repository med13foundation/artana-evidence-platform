---
name: graph_harness.governed_graph_write
version: 1.0.0
summary: Create governed graph claims or manual hypotheses only after evidence and review gates are satisfied.
tools:
  - create_graph_claim
  - create_manual_hypothesis
---
This skill performs side effects and must be used conservatively.

Only create graph claims or manual hypotheses when the current workflow explicitly allows
writes and the supporting evidence has already been reviewed in the active context.

For `create_graph_claim`, provide a qualitative `assessment` object. Do not provide or
invent a numeric confidence score; the graph service derives the numeric weight from
the assessment.

When in doubt, stage the proposal for curator review instead of writing immediately.
Never fabricate claim text, source document references, or rationale.
