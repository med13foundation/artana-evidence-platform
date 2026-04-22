# Core Concepts

## Research Space

Every graph route is scoped to a `space_id`, except service-admin dictionary and
control-plane routes.

Think of a graph space as the tenant container for:

- entities
- observations
- relations
- provenance
- claims
- reasoning paths
- concept sets

If two spaces have the same entity label, they still own different graph rows.

## Graph Space Registry

The graph service owns its own space registry in `graph_spaces`.

This is important because the service is standalone.

It cannot depend on platform tables at request time for core authorization.

The registry stores:

- the graph-space id
- slug and display name
- owner id
- service-local settings
- sync metadata from the upstream platform

## Graph Space Membership

The graph service also owns `graph_space_memberships`.

This table answers:

- who can access a space
- what role they have
- whether they are active

Common roles:

- `viewer`
- `researcher`
- `curator`
- `admin`
- `owner`

## Dictionary

The dictionary is the rules layer.

It defines:

- valid entity types
- valid relation types
- valid variable definitions
- value sets
- relation constraints
- transform registry entries

If the dictionary says a type or variable does not exist, the graph should not
use it.

## Entity

An entity is a graph node.

Examples:

- gene
- variant
- phenotype
- drug
- pathway
- patient
- publication

Important idea:

`entities` stores stable node identity and low-velocity metadata, not every fact
about that node.

## Entity Identifier

An entity identifier is a lookup key stored outside the main entity row.

Examples:

- HGNC symbol
- DOI
- HPO id
- MRN

This separation matters because identifiers can be sensitive.

`entity_identifiers` is where PHI-aware lookup behavior lives.

## Observation

An observation is one typed fact about one entity.

Examples:

- a patient has age `12`
- a variant has consequence `missense`
- a phenotype started on a certain date

Important rule:

one observation row has exactly one populated value column.

That is why the table has:

- `value_numeric`
- `value_text`
- `value_date`
- `value_coded`
- `value_boolean`
- `value_json`

## Provenance

Provenance explains where a row came from.

It can record:

- source type
- source reference
- extraction run id
- mapping method
- mapping confidence
- agent model
- raw input

This is how the graph stays auditable.

## Canonical Relation

A relation is the canonical graph edge.

Think:

`entity A --[relation_type]--> entity B`

Examples:

- `MED13 --ASSOCIATED_WITH--> congenital heart disease`
- `drug X --TARGETS--> pathway Y`

The canonical relation is what the graph exposes as accepted graph structure.

It carries:

- one source entity
- one relation type
- one target entity
- aggregated evidence metadata
- a curation lifecycle

## Relation Evidence

Canonical relations can have many evidence rows.

Each evidence row stores support for that canonical edge, such as:

- sentence
- evidence summary
- evidence tier
- confidence
- provenance
- source document reference

## Claim

A claim is not yet the canonical graph.

A claim is an extracted relation candidate recorded in `relation_claims`.

Use claims when you want to keep what was extracted before curation fully
decides whether it becomes a canonical relation.

That is why the service supports a claim-first workflow.

## Claim Participants

Claims can have structured participants in `claim_participants`.

This lets the service represent richer statements than a simple subject/object
pair.

Common participant roles:

- `SUBJECT`
- `OBJECT`
- `CONTEXT`
- `QUALIFIER`
- `MODIFIER`

## Claim Evidence

`claim_evidence` stores evidence attached directly to a claim before or during
review.

This is the evidence for the candidate statement, not necessarily the final
canonical relation.

## Claim Relations

Claims can also relate to other claims.

That data lives in `claim_relations`.

Examples:

- one claim supports another
- one claim contradicts another
- one claim refines another

This is what allows reasoning-chain and mechanism-chain views.

## Projection

Projection means turning claim-ledger state into canonical graph state.

The graph uses `relation_projection_sources` to remember which claims produced
which canonical relations.

That lineage answers:

- why does this canonical edge exist?
- which claims support it?
- was it manually created or claim-derived?

## Read Models

Read models are derived query tables.

They exist to make common reads fast and deterministic.

Examples:

- `entity_relation_summary`
- `entity_neighbors`
- `entity_claim_summary`
- `entity_mechanism_paths`

These are not the source of truth.

They are rebuilt from source-of-truth tables.

## Reasoning Path

A reasoning path is a derived, ordered explanation chain.

It is built from grounded claim relationships and stored in:

- `reasoning_paths`
- `reasoning_path_steps`

Use it when you want to explain a multi-step mechanism from one entity to
another.

## Concept Manager

Concept tables are a research-space semantic overlay on top of the global
dictionary.

They let a space define:

- concept sets
- concept members
- aliases
- concept links
- concept policies
- concept decisions

This is useful when the canonical dictionary is not enough for local curation
needs.

## One Clean Mental Picture

The easiest way to understand the service is:

- dictionary tables define what is allowed
- canonical graph tables store accepted graph truth
- claim tables store candidate or review-stage statements
- derived tables make reads and explanations faster
- control-plane tables decide who can access which graph space
