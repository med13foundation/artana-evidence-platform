# Graph Read-Model Ownership

This document records the initial Phase 4 ownership rules for graph query read
models.

## Core Rules

- Read models are derived query surfaces, not truth sources.
- Read models must be rebuildable from authoritative stores.
- Generic query read models belong to graph-core.
- Domain packs may eventually contribute pack-specific read models, but they do
  not own the rebuild framework, truth boundaries, or core generic model names.

## Authoritative Sources

Current graph-core read models may derive only from:

- claim ledger
- canonical graph
- projection lineage

Reasoning artifacts are explicitly excluded from Phase 4 generic read-model
inputs because they are derived outputs, not authoritative stores.

## Core Catalog

The initial graph-core catalog is defined in
`src/graph/core/read_model.py`:

- `entity_neighbors`
- `entity_relation_summary`
- `entity_claim_summary`

These entries define:

- ownership
- authoritative source boundaries
- incremental update trigger intent
- mandatory full rebuild support

Phase 4 now also has physical index tables, update hooks, rebuild jobs, and
benchmark coverage for the initial graph-core catalog.
