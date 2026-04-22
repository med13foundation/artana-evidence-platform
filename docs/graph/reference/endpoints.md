# Graph Endpoints

This document inventories every currently supported route in the standalone
graph service.

Exact request and response schemas live in `services/artana_evidence_db/openapi.json`.
Use this document for route discovery, access expectations, and capability
grouping.

## Access model

- `none`
  No authentication required.
- `member`
  Any authenticated caller with access to the graph space.
- `researcher+`
  Researcher, curator, admin, owner, or `graph_admin`.
- `curator+`
  Curator, admin, owner, or `graph_admin`.
- `graph_admin`
  Service-local control-plane admin claim.
- `member + graph_admin`
  The caller must be a graph-space member and also carry the `graph_admin`
  claim.

Feature-flagged routes:

- `GRAPH_ENABLE_ENTITY_EMBEDDINGS`
  Required for entity similarity and embedding refresh.
- `GRAPH_ENABLE_RELATION_SUGGESTIONS`
  Required for constrained relation suggestions.
- `GRAPH_ENABLE_HYPOTHESIS_GENERATION`
  Required for automatic hypothesis generation.
- `GRAPH_ENABLE_SEARCH_AGENT`
  Enables optional agent-assisted graph search. The route itself remains
  available even when the flag is off.

## Health

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | `none` | Basic liveness check for the standalone graph service. |

## Entities

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/entities` | `member` | List entities in a graph space. Supports `type`, `q`, and `ids` filters. |
| `POST` | `/v1/spaces/{space_id}/entities` | `researcher+` | Create or resolve an entity. |
| `GET` | `/v1/spaces/{space_id}/entities/{entity_id}` | `member` | Fetch one entity. |
| `PUT` | `/v1/spaces/{space_id}/entities/{entity_id}` | `researcher+` | Update one entity. |
| `DELETE` | `/v1/spaces/{space_id}/entities/{entity_id}` | `researcher+` | Delete one entity. |
| `GET` | `/v1/spaces/{space_id}/entities/{entity_id}/similar` | `member` | Find similar entities using hybrid graph plus embeddings. Requires `GRAPH_ENABLE_ENTITY_EMBEDDINGS=1`. |
| `POST` | `/v1/spaces/{space_id}/entities/embeddings/refresh` | `researcher+` | Refresh entity embeddings in a space or for a supplied entity subset. Requires `GRAPH_ENABLE_ENTITY_EMBEDDINGS=1`. |

## Observations And Provenance

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/observations` | `researcher+` | Record one observation. |
| `GET` | `/v1/spaces/{space_id}/observations` | `member` | List observations in a graph space. |
| `GET` | `/v1/spaces/{space_id}/observations/{observation_id}` | `member` | Fetch one observation. |
| `GET` | `/v1/spaces/{space_id}/provenance` | `member` | List provenance records in a graph space. |
| `GET` | `/v1/spaces/{space_id}/provenance/{provenance_id}` | `member` | Fetch one provenance record. |

## Claims And Claim Relations

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/claims` | `member` | List relation claims in a graph space. |
| `GET` | `/v1/spaces/{space_id}/claims/by-entity/{entity_id}` | `member` | List claims linked to one entity. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/participants` | `member` | List structured participants for one claim. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/evidence` | `member` | List claim evidence rows for one claim. |
| `PATCH` | `/v1/spaces/{space_id}/claims/{claim_id}` | `curator+` | Update relation-claim triage status and trigger materialization or detachment behavior. |
| `GET` | `/v1/spaces/{space_id}/claim-relations` | `member` | List claim-to-claim relation edges. |
| `POST` | `/v1/spaces/{space_id}/claim-relations` | `researcher+` | Create one claim-to-claim relation edge. |
| `PATCH` | `/v1/spaces/{space_id}/claim-relations/{relation_id}` | `curator+` | Update one claim-relation review status. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/mechanism-chain` | `member` | Traverse a reviewed mechanism-style claim chain. |

## Canonical Relations And Graph Read Models

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/relations` | `member` | List canonical relations in a graph space. |
| `POST` | `/v1/spaces/{space_id}/relations` | `member + graph_admin` | Create a canonical relation by creating a manual support claim and materializing it. |
| `PUT` | `/v1/spaces/{space_id}/relations/{relation_id}` | `curator+` | Update one canonical relation curation status. |
| `GET` | `/v1/spaces/{space_id}/relations/conflicts` | `member` | List mixed-polarity canonical relation conflicts derived from claims. |
| `GET` | `/v1/spaces/{space_id}/graph/export` | `member` | Export canonical graph nodes and edges. |
| `POST` | `/v1/spaces/{space_id}/graph/subgraph` | `member` | Build a bounded graph subgraph for rendering or inspection. |
| `GET` | `/v1/spaces/{space_id}/graph/neighborhood/{entity_id}` | `member` | Fetch one entity neighborhood subgraph. |
| `POST` | `/v1/spaces/{space_id}/graph/document` | `member` | Build a unified graph document with canonical, claim, and evidence overlays. |
| `GET` | `/v1/spaces/{space_id}/graph/views/{view_type}/{resource_id}` | `member` | Build one claim-aware domain view. Supported view types are pack-dependent. |

Current built-in pack view types:

- `biomedical`: `gene`, `variant`, `phenotype`, `paper`, `claim`
- `sports`: `team`, `athlete`, `match`, `report`, `claim`

## Search, Discovery, Reasoning, And Hypotheses

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/graph/search` | `member` | Run natural-language graph search. Agent augmentation is optional and controlled by `GRAPH_ENABLE_SEARCH_AGENT`. |
| `POST` | `/v1/spaces/{space_id}/graph/connections/discover` | `member` | Discover graph connections for one or more seed entities. Default source dispatch is pack-owned. |
| `POST` | `/v1/spaces/{space_id}/entities/{entity_id}/connections` | `member` | Discover graph connections for a single seed entity. Default source dispatch is pack-owned. |
| `POST` | `/v1/spaces/{space_id}/graph/relation-suggestions` | `researcher+` | Suggest constrained missing relations using hybrid graph plus embeddings. Requires `GRAPH_ENABLE_RELATION_SUGGESTIONS=1`. |
| `GET` | `/v1/spaces/{space_id}/reasoning-paths` | `member` | List persisted reasoning paths in a graph space. |
| `GET` | `/v1/spaces/{space_id}/reasoning-paths/{path_id}` | `member` | Retrieve one expanded reasoning path with linked claims and evidence. |
| `GET` | `/v1/spaces/{space_id}/hypotheses` | `member` | List hypothesis claims in a graph space. |
| `POST` | `/v1/spaces/{space_id}/hypotheses/manual` | `researcher+` | Create one manual hypothesis claim. |
| `POST` | `/v1/spaces/{space_id}/hypotheses/generate` | `researcher+` | Auto-generate reviewable hypotheses from graph exploration. Requires `GRAPH_ENABLE_HYPOTHESIS_GENERATION=1`. |

## Concept Governance

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/concepts/sets` | `member` | List concept sets in a graph space. |
| `POST` | `/v1/spaces/{space_id}/concepts/sets` | `researcher+` | Create one concept set. |
| `GET` | `/v1/spaces/{space_id}/concepts/members` | `member` | List concept members in a graph space. |
| `POST` | `/v1/spaces/{space_id}/concepts/members` | `researcher+` | Create one concept member. |
| `GET` | `/v1/spaces/{space_id}/concepts/aliases` | `member` | List concept aliases in a graph space. |
| `POST` | `/v1/spaces/{space_id}/concepts/aliases` | `researcher+` | Create one concept alias. |
| `GET` | `/v1/spaces/{space_id}/concepts/policy` | `member` | Fetch the active concept policy for a graph space. |
| `PUT` | `/v1/spaces/{space_id}/concepts/policy` | `curator+` | Upsert the active concept policy. |
| `GET` | `/v1/spaces/{space_id}/concepts/decisions` | `member` | List concept decisions in a graph space. |
| `POST` | `/v1/spaces/{space_id}/concepts/decisions/propose` | `researcher+` | Propose one concept decision. |
| `PATCH` | `/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status` | `curator+` | Update one concept-decision status. |

## Space Control Plane

All routes in this section require `graph_admin`.

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/admin/spaces` | `graph_admin` | List graph-space registry entries. |
| `GET` | `/v1/admin/spaces/{space_id}` | `graph_admin` | Fetch one graph-space registry entry. |
| `PUT` | `/v1/admin/spaces/{space_id}` | `graph_admin` | Create or update one graph-space registry entry. |
| `GET` | `/v1/admin/spaces/{space_id}/memberships` | `graph_admin` | List graph-space memberships. |
| `PUT` | `/v1/admin/spaces/{space_id}/memberships/{user_id}` | `graph_admin` | Create or update one graph-space membership. |
| `POST` | `/v1/admin/spaces/{space_id}/sync` | `graph_admin` | Atomically sync graph-space registry state and membership snapshot from the platform control plane. |

## Operational Maintenance And Run History

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/claim-participants/backfill` | `researcher+` | Backfill structured participants for relation claims in one graph space. |
| `GET` | `/v1/spaces/{space_id}/claim-participants/coverage` | `member` | Report participant coverage and unresolved endpoint rates for one graph space. |
| `GET` | `/v1/admin/projections/readiness` | `graph_admin` | Audit global projection readiness and persist a run record. |
| `POST` | `/v1/admin/projections/repair` | `graph_admin` | Repair global projection-readiness issues and persist a run record. |
| `POST` | `/v1/admin/reasoning-paths/rebuild` | `graph_admin` | Rebuild persisted reasoning paths globally or for one space and persist a run record. |
| `GET` | `/v1/admin/operations/runs` | `graph_admin` | List recorded graph-service operation runs. |
| `GET` | `/v1/admin/operations/runs/{run_id}` | `graph_admin` | Fetch one recorded graph-service operation run. |

## Dictionary Governance

All routes in this section require `graph_admin`.

### Search, Policies, Constraints, And Changelog

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/dictionary/search` | `graph_admin` | Search graph dictionary entries. |
| `GET` | `/v1/dictionary/search/by-domain/{domain_context}` | `graph_admin` | List graph dictionary entries by domain context. |
| `POST` | `/v1/dictionary/reembed` | `graph_admin` | Recompute dictionary description embeddings. |
| `GET` | `/v1/dictionary/resolution-policies` | `graph_admin` | List graph dictionary entity-resolution policies. |
| `GET` | `/v1/dictionary/relation-constraints` | `graph_admin` | List graph dictionary relation constraints. |
| `POST` | `/v1/dictionary/relation-constraints` | `graph_admin` | Create one graph dictionary relation constraint. |
| `GET` | `/v1/dictionary/changelog` | `graph_admin` | List graph dictionary changelog entries. |

### Variables And Value Sets

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/dictionary/variables` | `graph_admin` | List graph dictionary variables. |
| `POST` | `/v1/dictionary/variables` | `graph_admin` | Create one graph dictionary variable. |
| `PATCH` | `/v1/dictionary/variables/{variable_id}/review-status` | `graph_admin` | Set variable review status. |
| `POST` | `/v1/dictionary/variables/{variable_id}/revoke` | `graph_admin` | Revoke one variable. |
| `POST` | `/v1/dictionary/variables/{variable_id}/merge` | `graph_admin` | Merge one variable into another. |
| `GET` | `/v1/dictionary/value-sets` | `graph_admin` | List graph dictionary value sets. |
| `POST` | `/v1/dictionary/value-sets` | `graph_admin` | Create one graph dictionary value set. |
| `GET` | `/v1/dictionary/value-sets/{value_set_id}/items` | `graph_admin` | List value-set items for one value set. |
| `POST` | `/v1/dictionary/value-sets/{value_set_id}/items` | `graph_admin` | Create one value-set item. |
| `PATCH` | `/v1/dictionary/value-set-items/{value_set_item_id}/active` | `graph_admin` | Activate or deactivate one value-set item. |

### Entity Types

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/dictionary/entity-types` | `graph_admin` | List graph dictionary entity types. |
| `GET` | `/v1/dictionary/entity-types/{entity_type_id}` | `graph_admin` | Fetch one graph dictionary entity type. |
| `POST` | `/v1/dictionary/entity-types` | `graph_admin` | Create one graph dictionary entity type. |
| `PATCH` | `/v1/dictionary/entity-types/{entity_type_id}/review-status` | `graph_admin` | Set entity-type review status. |
| `POST` | `/v1/dictionary/entity-types/{entity_type_id}/revoke` | `graph_admin` | Revoke one entity type. |
| `POST` | `/v1/dictionary/entity-types/{entity_type_id}/merge` | `graph_admin` | Merge one entity type into another. |

### Relation Types And Relation Synonyms

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/dictionary/relation-types` | `graph_admin` | List graph dictionary relation types. |
| `GET` | `/v1/dictionary/relation-types/{relation_type_id}` | `graph_admin` | Fetch one graph dictionary relation type. |
| `POST` | `/v1/dictionary/relation-types` | `graph_admin` | Create one graph dictionary relation type. |
| `PATCH` | `/v1/dictionary/relation-types/{relation_type_id}/review-status` | `graph_admin` | Set relation-type review status. |
| `POST` | `/v1/dictionary/relation-types/{relation_type_id}/revoke` | `graph_admin` | Revoke one relation type. |
| `POST` | `/v1/dictionary/relation-types/{relation_type_id}/merge` | `graph_admin` | Merge one relation type into another. |
| `GET` | `/v1/dictionary/relation-synonyms` | `graph_admin` | List graph dictionary relation synonyms. |
| `GET` | `/v1/dictionary/relation-synonyms/resolve` | `graph_admin` | Resolve one graph dictionary relation synonym. |
| `POST` | `/v1/dictionary/relation-synonyms` | `graph_admin` | Create one graph dictionary relation synonym. |
| `PATCH` | `/v1/dictionary/relation-synonyms/{synonym_id}/review-status` | `graph_admin` | Set relation-synonym review status. |
| `POST` | `/v1/dictionary/relation-synonyms/{synonym_id}/revoke` | `graph_admin` | Revoke one relation synonym. |

### Transforms

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/v1/dictionary/transforms` | `graph_admin` | List graph dictionary transforms. |
| `POST` | `/v1/dictionary/transforms/{transform_id}/verify` | `graph_admin` | Run transform fixture verification. |
| `PATCH` | `/v1/dictionary/transforms/{transform_id}/promote` | `graph_admin` | Promote one graph dictionary transform to production use. |

## Contract Notes

- The platform app no longer publishes supported graph APIs under the
  `/research-spaces/{space_id}/` prefix.
- The generated OpenAPI artifact at `services/artana_evidence_db/openapi.json` is the
  schema-level contract source of truth.
- Generated TypeScript consumers should use
  `services/artana_evidence_db/artana-evidence-db.generated.ts`.
