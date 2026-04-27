---
name: graph_harness.source_relevance
version: 1.0.0
summary: Select relevant source records for a research goal while preserving provenance, caveats, and review boundaries.
tools: []
requires_capabilities: []
---

Use this skill when a harness must decide which source-search records are worth
turning into candidate evidence.

Treat the user's goal, instructions, inclusion criteria, exclusion criteria,
population or context, preferred evidence types, and priority outcomes as the
selection policy. Prefer records that directly match the goal, add novelty to
the research space, and have useful source provenance.

Always separate three layers:

- candidate evidence: selected source records and extracted proposals;
- reviewed evidence: proposals or review items that a reviewer has accepted;
- trusted graph knowledge: approved facts written through governed graph paths.

Never present selected records as truth. The output should explain why each
record was selected, skipped, or deferred. Include source family, source id,
search id, record index or hash, relevance signals, duplicate signals, and
scientific caveats.

Downgrade or defer records when they are off-topic, duplicate prior work, match
exclusion criteria, contain weak or indirect evidence, make association-only
claims, conflict with prior evidence, or lack enough provenance for review.

When handoffs are allowed, create them only for selected records and keep all
downstream extraction review-gated.
