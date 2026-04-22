---
name: graph_harness.claim_validation
version: 1.0.0
summary: Validate claim consistency, participants, and evidence before governed graph writes.
tools:
  - list_claims_by_entity
  - list_claim_participants
  - list_claim_evidence
  - list_relation_conflicts
---
Validate before writing.

Check whether equivalent or conflicting claims already exist, inspect claim participants, and
review attached evidence before recommending any graph mutation.

Escalate conflicts, missing participants, or thin evidence instead of forcing a write.
When a claim is already represented adequately, prefer review guidance over duplicate creation.
