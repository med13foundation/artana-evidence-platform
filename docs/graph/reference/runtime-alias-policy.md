# Graph Runtime Alias Policy

Recorded on `2026-03-13`.
Removed on `2026-03-13`.

`GRAPH_*` env names are now the only supported graph runtime contract.

This document is retained as a historical removal record for the graph-specific
runtime aliases eliminated during Phase 1 neutralization.

## Removed Aliases

The removed graph alias set was:

- `MED13_DEV_JWT_SECRET`
  Replaced by `GRAPH_JWT_SECRET`
- `MED13_BYPASS_TEST_AUTH_HEADERS`
  Replaced by `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `MED13_ENABLE_ENTITY_EMBEDDINGS`
  Replaced by `GRAPH_ENABLE_ENTITY_EMBEDDINGS`
- `MED13_ENABLE_RELATION_SUGGESTIONS`
  Replaced by `GRAPH_ENABLE_RELATION_SUGGESTIONS`
- `MED13_ENABLE_HYPOTHESIS_GENERATION`
  Replaced by `GRAPH_ENABLE_HYPOTHESIS_GENERATION`
- `MED13_ENABLE_GRAPH_SEARCH_AGENT`
  Replaced by `GRAPH_ENABLE_SEARCH_AGENT`
- `MED13_RELATION_AUTOPROMOTE_*`
  Replaced by `GRAPH_RELATION_AUTOPROMOTE_*`

## Current Enforcement

- policy validation:
  `scripts/validate_graph_phase1_alias_policy.py`
- Make target:
  `make graph-phase1-alias-check`

## Enforcement Outcome

- graph runtime code no longer reads the removed aliases
- graph-facing docs only describe `GRAPH_*` env names as the current contract
- graph deployment tooling only publishes neutral `GRAPH_*` env names
- the Phase 1 architecture gate fails if removed aliases reappear in live graph
  runtime surfaces
