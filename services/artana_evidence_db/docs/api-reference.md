# API Reference

Base URL examples in this file assume:

```bash
export GRAPH_URL="http://localhost:8090"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
```

All authenticated examples use:

```bash
-H "Authorization: Bearer $TOKEN"
```

## Endpoint Groups

## 1. Health

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | Returns service health status. |

Example:

```bash
curl -s "$GRAPH_URL/health" \
  -H "Authorization: Bearer $TOKEN"
```

## 2. Entity API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/entities` | Lists entities in one graph space. |
| `POST` | `/v1/spaces/{space_id}/entities` | Creates one entity. |
| `GET` | `/v1/spaces/{space_id}/entities/{entity_id}` | Returns one entity. |
| `PUT` | `/v1/spaces/{space_id}/entities/{entity_id}` | Replaces one entity. |
| `DELETE` | `/v1/spaces/{space_id}/entities/{entity_id}` | Deletes one entity. |

## 3. Observation API

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/observations` | Creates one observation. |
| `GET` | `/v1/spaces/{space_id}/observations` | Lists observations. |
| `GET` | `/v1/spaces/{space_id}/observations/{observation_id}` | Returns one observation. |

## 4. Provenance API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/provenance` | Lists provenance rows. |
| `GET` | `/v1/spaces/{space_id}/provenance/{provenance_id}` | Returns one provenance row. |

## 5. Canonical Relation And Graph Read API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/relations` | Lists canonical relations. |
| `POST` | `/v1/spaces/{space_id}/relations` | Creates one canonical relation. |
| `PUT` | `/v1/spaces/{space_id}/relations/{relation_id}` | Updates curation state for one canonical relation. |
| `POST` | `/v1/spaces/{space_id}/relations/suggestions` | Requests deterministic relation suggestions. |
| `POST` | `/v1/spaces/{space_id}/graph/subgraph` | Returns a filtered graph subgraph. |
| `GET` | `/v1/spaces/{space_id}/graph/neighborhood/{entity_id}` | Returns one-hop neighborhood around an entity. |

## 6. Graph Document And Graph View API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/graph/export` | Exports graph data for one space. |
| `POST` | `/v1/spaces/{space_id}/graph/document` | Builds a unified graph document. |
| `GET` | `/v1/spaces/{space_id}/graph/views/{view_type}/{resource_id}` | Returns one graph view payload. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/mechanism-chain` | Returns one claim-centered mechanism chain view. |

## 7. Claim Ledger API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/claims` | Lists relation claims. |
| `POST` | `/v1/spaces/{space_id}/claims` | Creates one relation claim. |
| `GET` | `/v1/spaces/{space_id}/claims/by-entity/{entity_id}` | Lists claims anchored to one entity. |
| `PATCH` | `/v1/spaces/{space_id}/claims/{claim_id}` | Updates review or triage state for one claim. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/participants` | Lists structured participants for one claim. |
| `GET` | `/v1/spaces/{space_id}/claims/{claim_id}/evidence` | Lists evidence rows for one claim. |
| `GET` | `/v1/spaces/{space_id}/relations/conflicts` | Lists claim-vs-relation conflicts. |

Claim writes are replay-safe when the caller provides either request
`source_ref` or the `Idempotency-Key` header. AI-authored claim writes must
include `agent_run_id` and an `ai_provenance` envelope with model, prompt,
input hash, rationale, and evidence references. Claims blocked by dictionary
review can remain in the ledger, but they cannot promote to canonical
relations until the dictionary has an active exact `ALLOWED` or `EXPECTED`
relation constraint for the triple.

## 8. Validation API

Validation routes check candidate graph or dictionary writes without persisting
new rows. Use them before AI-assisted writes when the caller needs an actionable
reason, a stable code, and any next dictionary proposal action.

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/validate/entity` | Validates one entity payload. |
| `POST` | `/v1/spaces/{space_id}/validate/observation` | Validates one observation payload. |
| `POST` | `/v1/spaces/{space_id}/validate/triple` | Validates one relation triple. |
| `POST` | `/v1/spaces/{space_id}/validate/claim` | Validates one claim and reports duplicate or conflicting claim ids. |
| `POST` | `/v1/dictionary/validate/entity-type` | Validates one dictionary entity type id. |
| `POST` | `/v1/dictionary/validate/relation-type` | Validates one dictionary relation type id. |
| `POST` | `/v1/dictionary/validate/relation-constraint` | Validates one dictionary relation constraint triple. |

Stable validation codes are published in OpenAPI on
`KernelGraphValidationResponse.code`. Current codes are `allowed`,
`unknown_entity_type`, `inactive_entity_type`, `unknown_relation_type`,
`invalid_relation_type`, `relation_constraint_not_allowed`,
`relation_constraint_review_only`, `missing_required_identifier`,
`duplicate_entity_candidate`, `unknown_entity`, `unknown_subject`,
`unknown_variable`, `duplicate_claim`, `conflicting_claim`,
`missing_ai_provenance`, `invalid_value_for_variable`, `missing_provenance`,
`unknown_provenance`, `cross_space_provenance`, `insufficient_evidence`, and
`permission_denied`.

Example:

```bash
curl -s "$GRAPH_URL/v1/spaces/$SPACE_ID/validate/claim" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_entity_id": "22222222-2222-2222-2222-222222222222",
    "target_entity_id": "33333333-3333-3333-3333-333333333333",
    "relation_type": "ASSOCIATED_WITH",
    "assessment": {
      "support_band": "SUPPORTED",
      "grounding_level": "SPAN",
      "mapping_status": "RESOLVED",
      "speculation_level": "DIRECT",
      "confidence_rationale": "Evidence sentence supports the claim."
    },
    "claim_text": "MED13 is associated with developmental delay.",
    "source_document_ref": "pmid:123456"
  }'
```

Duplicate or conflicting claim responses set `valid` to `false`, `severity` to
`blocking`, and include the blocking `claim_ids`.

## 9. Claim Relation API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/claim-relations` | Lists claim-to-claim edges. |
| `POST` | `/v1/spaces/{space_id}/claim-relations` | Creates one claim-to-claim edge. |
| `PATCH` | `/v1/spaces/{space_id}/claim-relations/{relation_id}` | Reviews one claim-to-claim edge. |

## 10. Reasoning Path API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/reasoning-paths` | Lists derived reasoning paths. |
| `GET` | `/v1/spaces/{space_id}/reasoning-paths/{path_id}` | Returns one reasoning path with steps. |

## 11. Hypothesis API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/hypotheses` | Lists hypotheses in one graph space. |
| `POST` | `/v1/spaces/{space_id}/hypotheses/manual` | Creates a manual hypothesis. |

## 12. Concept Governance API

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/concepts/sets` | Lists concept sets. |
| `POST` | `/v1/spaces/{space_id}/concepts/sets` | Creates one concept set. |
| `GET` | `/v1/spaces/{space_id}/concepts/members` | Lists concept members. |
| `POST` | `/v1/spaces/{space_id}/concepts/members` | Creates one concept member. |
| `GET` | `/v1/spaces/{space_id}/concepts/aliases` | Lists concept aliases. |
| `POST` | `/v1/spaces/{space_id}/concepts/aliases` | Creates one concept alias. |
| `GET` | `/v1/spaces/{space_id}/concepts/policy` | Returns the active concept policy. |
| `PUT` | `/v1/spaces/{space_id}/concepts/policy` | Upserts the active concept policy. |
| `GET` | `/v1/spaces/{space_id}/concepts/decisions` | Lists concept governance decisions. |
| `POST` | `/v1/spaces/{space_id}/concepts/decisions/propose` | Proposes one concept decision. |
| `PATCH` | `/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status` | Updates concept decision status. |

## 13. Dictionary Governance API

These routes are service-admin routes under `/v1/dictionary`.
They require a bearer token with the graph-service `graph_admin` claim set to `true`.
Use `GET /v1/dictionary/domain-contexts` to discover the valid `domain_context`
ids accepted by dictionary creation routes. On fresh installs, `general` is always
available.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/dictionary/domain-contexts` | Lists approved dictionary domain contexts. |
| `GET` | `/v1/dictionary/search/by-domain/{domain_context}` | Lists dictionary entries by domain. |
| `GET` | `/v1/dictionary/resolution-policies` | Lists entity resolution policies. |
| `GET` | `/v1/dictionary/relation-constraints` | Lists relation constraints. |
| `POST` | `/v1/dictionary/relation-constraints` | Creates one relation constraint. |
| `GET` | `/v1/dictionary/changelog` | Lists dictionary changelog entries. |
| `GET` | `/v1/dictionary/variables` | Lists variable definitions. |
| `POST` | `/v1/dictionary/variables` | Creates one variable definition. |
| `PATCH` | `/v1/dictionary/variables/{variable_id}/review-status` | Updates variable review status. |
| `POST` | `/v1/dictionary/variables/{variable_id}/revoke` | Revokes one variable definition. |
| `POST` | `/v1/dictionary/variables/{variable_id}/merge` | Merges variable definitions. |
| `GET` | `/v1/dictionary/value-sets` | Lists value sets. |
| `POST` | `/v1/dictionary/value-sets` | Creates one value set. |
| `GET` | `/v1/dictionary/value-sets/{value_set_id}/items` | Lists items in one value set. |
| `POST` | `/v1/dictionary/value-sets/{value_set_id}/items` | Creates one value-set item. |
| `PATCH` | `/v1/dictionary/value-set-items/{value_set_item_id}/active` | Activates or deactivates one value-set item. |
| `GET` | `/v1/dictionary/entity-types` | Lists entity types. |
| `GET` | `/v1/dictionary/entity-types/{entity_type_id}` | Returns one entity type. |
| `POST` | `/v1/dictionary/entity-types` | Creates one entity type. |
| `PATCH` | `/v1/dictionary/entity-types/{entity_type_id}/review-status` | Updates entity-type review status. |
| `POST` | `/v1/dictionary/entity-types/{entity_type_id}/revoke` | Revokes one entity type. |
| `POST` | `/v1/dictionary/entity-types/{entity_type_id}/merge` | Merges entity types. |
| `GET` | `/v1/dictionary/relation-types` | Lists relation types. |
| `GET` | `/v1/dictionary/relation-types/{relation_type_id}` | Returns one relation type. |
| `POST` | `/v1/dictionary/relation-types` | Creates one relation type. |
| `PATCH` | `/v1/dictionary/relation-types/{relation_type_id}/review-status` | Updates relation-type review status. |
| `POST` | `/v1/dictionary/relation-types/{relation_type_id}/revoke` | Revokes one relation type. |
| `POST` | `/v1/dictionary/relation-types/{relation_type_id}/merge` | Merges relation types. |
| `GET` | `/v1/dictionary/relation-synonyms` | Lists relation synonyms. |
| `GET` | `/v1/dictionary/relation-synonyms/resolve` | Resolves a relation synonym deterministically. |
| `POST` | `/v1/dictionary/relation-synonyms` | Creates one relation synonym. |
| `PATCH` | `/v1/dictionary/relation-synonyms/{synonym_id}/review-status` | Updates synonym review status. |
| `POST` | `/v1/dictionary/relation-synonyms/{synonym_id}/revoke` | Revokes one synonym. |
| `GET` | `/v1/dictionary/transforms` | Lists transform registry entries. |
| `POST` | `/v1/dictionary/transforms/{transform_id}/verify` | Verifies one transform. |
| `PATCH` | `/v1/dictionary/transforms/{transform_id}/promote` | Promotes one transform. |

Dictionary proposal routes stage changes for governed review before they become
official dictionary state. Proposal creation is replay-safe through either
request `source_ref` or the `Idempotency-Key` header.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/dictionary/proposals` | Lists dictionary proposals. |
| `POST` | `/v1/dictionary/proposals/domain-contexts` | Proposes one domain context. |
| `POST` | `/v1/dictionary/proposals/entity-types` | Proposes one entity type. |
| `POST` | `/v1/dictionary/proposals/relation-types` | Proposes one relation type. |
| `POST` | `/v1/dictionary/proposals/relation-constraints` | Proposes one relation constraint. |
| `POST` | `/v1/dictionary/proposals/relation-synonyms` | Proposes one relation synonym. |
| `POST` | `/v1/dictionary/proposals/variables` | Proposes one variable definition. |
| `POST` | `/v1/dictionary/proposals/value-sets` | Proposes one value set. |
| `POST` | `/v1/dictionary/proposals/value-sets/{value_set_id}/items` | Proposes one value-set item. |
| `GET` | `/v1/dictionary/proposals/{proposal_id}` | Returns one proposal. |
| `POST` | `/v1/dictionary/proposals/{proposal_id}/approve` | Approves and applies one proposal. |
| `POST` | `/v1/dictionary/proposals/{proposal_id}/reject` | Rejects one proposal without changing official dictionary state. |
| `POST` | `/v1/dictionary/proposals/{proposal_id}/request-changes` | Sends one proposal back for changes. |
| `POST` | `/v1/dictionary/proposals/{proposal_id}/merge` | Marks one proposal as merged into an existing dictionary entry. |

## 14. Domain Pack API

Domain pack routes describe the installed vocabulary packs and let graph admins
explicitly seed or repair one graph space for one pack version. Service startup
does not seed every existing space.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/domain-packs` | Lists registered domain packs and the active pack. |
| `GET` | `/v1/domain-packs/active` | Returns the active domain pack summary, including its version. |
| `GET` | `/v1/domain-packs/{pack_name}` | Returns one registered domain pack summary. |
| `GET` | `/v1/domain-packs/{pack_name}/spaces/{space_id}/seed-status` | Returns recorded seed status for one pack version in one space. |
| `POST` | `/v1/domain-packs/{pack_name}/spaces/{space_id}/seed` | Seeds one pack version into one space; repeated calls are idempotent. |
| `POST` | `/v1/domain-packs/{pack_name}/spaces/{space_id}/repair` | Re-runs pack-owned seed work and records a repair operation. |

Seed status records `pack_name`, `pack_version`, `seed_count`,
`repair_count`, the last operation, and metadata describing the seeded pack.

## 15. Graph Space Control-Plane API

These routes are service-admin routes for graph-space registry and memberships.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/admin/spaces/{space_id}` | Returns one graph-space registry entry. |
| `PUT` | `/v1/admin/spaces/{space_id}` | Upserts one graph-space registry entry. |
| `GET` | `/v1/admin/spaces/{space_id}/memberships` | Lists memberships in one graph space. |
| `PUT` | `/v1/admin/spaces/{space_id}/memberships/{user_id}` | Upserts one graph-space membership. |
| `POST` | `/v1/admin/spaces/{space_id}/sync` | Atomically syncs a graph space and its memberships. |

Space create and sync operations only manage registry and membership state. Use
the Domain Pack API to seed dictionary defaults and pack-owned space concepts.

## 16. Maintenance And Admin Operations API

These routes are service-admin or elevated maintenance routes.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/admin/projections/readiness` | Audits projection readiness across graph state. |
| `POST` | `/v1/admin/projections/repair` | Repairs projection lineage and read-model issues. |
| `POST` | `/v1/admin/reasoning-paths/rebuild` | Rebuilds derived reasoning paths. |
| `POST` | `/v1/spaces/{space_id}/claim-participants/backfill` | Backfills structured claim participants. |
| `GET` | `/v1/spaces/{space_id}/claim-participants/coverage` | Returns claim-participant coverage stats. |
| `GET` | `/v1/admin/operations/runs` | Lists recorded maintenance operation runs. |
| `GET` | `/v1/admin/operations/runs/{run_id}` | Returns one maintenance operation run. |

## Which Routes Most Users Need First

If you are learning the service, start here:

1. `/health`
2. `/v1/spaces/{space_id}/entities`
3. `/v1/spaces/{space_id}/relations`
4. `/v1/spaces/{space_id}/claims`
5. `/v1/spaces/{space_id}/validate/claim`
6. `/v1/spaces/{space_id}/graph/export`

## Where To Go For Payload Details

For exact request and response schemas, use one of these:

- interactive docs at `/docs`
- [openapi.json](/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_db/openapi.json)

For a minimal external-project flow, see
`services/artana_evidence_db/examples/http_only_client_flow.py`. It uses only
HTTP calls: health, domain-pack discovery, graph-space upsert, pack seed,
entity validation and creation, claim validation and creation, and graph export.
