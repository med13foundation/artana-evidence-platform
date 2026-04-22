# Data Model

## The Main Split

The database model is easiest to understand if you split it into five groups.

1. Control-plane tables
2. Canonical graph tables
3. Claim-first curation tables
4. Derived read-model tables
5. Governance tables

## 1. Control-Plane Tables

These tables make the standalone service self-sufficient.

| Table | What it stores | Why it exists |
| --- | --- | --- |
| `graph_spaces` | graph-space registry entries | lets the service own tenant metadata |
| `graph_space_memberships` | who can access each graph space | lets the service authorize requests locally |
| `graph_operation_runs` | admin and maintenance run history | keeps repair, audit, rebuild, and backfill activity traceable |
| `graph_pack_seed_status` | pack seed version ledger | records which domain pack/version was explicitly seeded or repaired per space |

## 2. Canonical Graph Tables

These are the source-of-truth graph tables.

| Table | What it stores | Notes |
| --- | --- | --- |
| `entities` | graph nodes | one row per node in one space |
| `entity_identifiers` | lookup keys for entities | separated for PHI-aware handling |
| `observations` | typed facts about entities | one value column populated per row |
| `relations` | canonical graph edges | one accepted edge between source and target |
| `relation_evidence` | evidence rows supporting a relation | many evidence rows can point to one relation |
| `provenance` | source and extraction lineage | explains where graph data came from |

### Canonical Graph Flow

```text
dictionary rules
    ->
entities
    ->
observations and relations
    ->
relation_evidence and provenance
```

## 3. Claim-First Curation Tables

These tables hold extracted or staged relation statements before, during, or
alongside canonicalization.

| Table | What it stores | Notes |
| --- | --- | --- |
| `relation_claims` | extracted relation candidates | one ledger row per candidate statement |
| `claim_participants` | structured claim endpoints and qualifiers | supports richer claim structure |
| `claim_evidence` | evidence attached directly to a claim | supports review and traceability |
| `claim_relations` | semantic edges between claims | used for support, contradiction, refinement, and chain building |
| `relation_projection_sources` | lineage from claims to canonical relations | shows which claims produced which accepted edges |

`relation_claims.source_ref` is the replay key for idempotent claim writes.
AI-authored claims also store an `ai_provenance` object in claim metadata so a
reviewer can see which model, prompt, input hash, rationale, and evidence
references produced the claim. `relation_projection_sources` is the durable
lineage table: accepting a claim does not secretly create dictionary rules, and
projection requires an active exact relation constraint with promotable
governance.

### Claim-First Flow

```text
source document or extraction run
    ->
relation_claims
    ->
claim_evidence and claim_participants
    ->
review and projection
    ->
relations
```

## 4. Derived Read-Model Tables

These tables are optimized views, not primary truth.

| Table | What it stores | Why it exists |
| --- | --- | --- |
| `entity_relation_summary` | per-entity relation counts | fast entity summary reads |
| `entity_neighbors` | one-hop graph adjacency | fast neighborhood reads |
| `entity_claim_summary` | per-entity claim counts | quick claim-centered overview |
| `entity_mechanism_paths` | derived mechanism path view | faster mechanism-oriented reads |
| `reasoning_paths` | derived multi-step paths | durable explanation objects |
| `reasoning_path_steps` | ordered path steps | explains each reasoning path in detail |

Important rule:

If a derived table is wrong, rebuild it from the canonical and claim source
tables. Do not treat it as primary truth.

## 5. Governance Tables

These tables define the vocabulary and curation overlays.

### Dictionary Governance

Important dictionary tables:

- `dictionary_domain_contexts`
- `dictionary_entity_types`
- `dictionary_relation_types`
- `variable_definitions`
- `value_sets`
- `value_set_items`
- `relation_constraints`
- `transform_registry`
- `entity_resolution_policies`
- `dictionary_proposals`
- `dictionary_changelog`

The dictionary answers:

- which entity types exist
- which relation types exist
- which variables can be observed
- which values are allowed
- which relation endpoints are legal

`dictionary_proposals` is the governed staging ledger for new dictionary ideas.
Approving a proposal creates official dictionary state; rejecting one leaves the
official dictionary unchanged; merging one points to an existing canonical entry.
Proposal lifecycle changes are auditable through `dictionary_changelog`.

### Concept Governance

Important concept tables:

- `concept_sets`
- `concept_members`
- `concept_aliases`
- `concept_links`
- `concept_policies`
- `concept_decisions`
- `concept_harness_results`

These tables let one research space create a semantic overlay without changing
the shared dictionary for everyone else.

### Pack Seed Ledger

`graph_pack_seed_status` records explicit domain-pack seeding by graph space.
Each row stores `research_space_id`, `pack_name`, `pack_version`, seed and
repair counters, last operation, timestamps, and pack metadata. This means the
service can prove which pack version prepared a space, rerun repair safely, and
avoid hidden startup mutations across every existing space.

## The Three Most Important Tables

If you only remember three tables, remember these:

### `entities`

This is the node table.

Key columns:

- `id`
- `research_space_id`
- `entity_type`
- `display_label`
- `metadata_payload`

### `observations`

This is the typed fact table.

Key columns:

- `subject_id`
- `variable_id`
- one populated typed value column
- `observed_at`
- `provenance_id`
- `confidence`

### `relations`

This is the canonical edge table.

Key columns:

- `source_id`
- `relation_type`
- `target_id`
- `aggregate_confidence`
- `source_count`
- `curation_status`

## The Most Important Relationship Pattern

```text
graph_spaces
    ->
entities
    ->
observations

graph_spaces
    ->
entities
    ->
relations
    ->
relation_evidence

provenance
    -> observations
provenance
    -> relations
provenance
    -> relation_evidence
```

## Why The Model Looks Like This

The design goals are:

- multi-tenant by graph space
- auditable through provenance
- safe for PHI-aware identifiers
- able to keep extracted claims separate from accepted graph truth
- fast to read through derived projections
- flexible across domains because the dictionary defines the schema surface
