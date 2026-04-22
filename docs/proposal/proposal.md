# RFC: Claim Graph Overlay (Revised)

**Status:** Draft
**Author:** MED13 Engineering
**Date:** 2026-03-04
**Scope:** Kernel schema evolution, extraction pipeline, search, curation UI

---

## 1. Summary

This RFC upgrades claim-first curation from a flat ledger into a traversable claim graph by introducing two additive tables:

1. `claim_participants`: N-ary, role-based entity participation per claim.
2. `claim_relations`: directed claim-to-claim edges for contradiction, support, and mechanism chains.

The direction remains unchanged. This revision tightens integrity and governance to match existing kernel standards:

1. Cross-space integrity is enforced at the database layer via composite foreign keys.
2. Duplicate claim-to-claim edges are prevented with a unique constraint.
3. `claim_participants` is the canonical structural representation for retrieval/traversal.
4. Existing `metadata_payload.concept_refs` remains as extraction provenance, not retrieval truth.
5. `claim_relations` carries richer provenance and review lifecycle fields.
6. Stale references are corrected (`entities.display_label`, `/research-spaces/...` route prefix).

---

## 2. Problem Statement

The kernel canonical graph stores binary edges:

```
Entity (source_id) --[relation_type]--> Entity (target_id)
```

This remains correct for the curated “current belief” layer (`relations`).

The claim layer (`relation_claims`) correctly captures uncertainty and curation lifecycle, but today has two structural gaps:

1. Claim structure is effectively binary (`source_label` / `target_label`) and entity IDs are commonly embedded in metadata instead of indexed relational slots.
2. Claims are isolated rows; there is no persistent claim-to-claim topology for contradiction/support/refinement/mechanistic chains.

Result: entity-centered retrieval, mechanistic path traversal, and durable contradiction graphs are harder than they should be, and rely on ad hoc query-time logic.

---

## 3. Design Goals and Non-Goals

### 3.1 Goals

1. Make claims traversable by entity using indexed relational links.
2. Support N-ary claim structure without breaking existing extraction flow.
3. Persist claim-to-claim relationships for contradiction and mechanism paths.
4. Preserve strict research-space isolation guarantees at the DB level.
5. Preserve provenance-first governance and explicit review lifecycle.

### 3.2 Non-Goals

1. Replacing canonical `relations` as the curated convenience graph.
2. Breaking existing `relation_claims` writes.
3. Introducing a full ontology-governed relation-type system for claim-to-claim links in V1.
4. Reintroducing public canonical relation writes outside claim-backed projection materialization.

---

## 4. Current State (Accurate to Codebase)

### 4.1 Existing tables that remain

| Table | Purpose | Key fields |
|---|---|---|
| `entities` | Graph nodes | `id`, `entity_type`, `display_label`, `research_space_id` |
| `relations` | Canonical binary edges | `source_id`, `relation_type`, `target_id`, `research_space_id` |
| `relation_claims` | Claim-first ledger | `source_label`, `target_label`, `polarity`, `claim_text`, `metadata_payload` |
| `claim_evidence` | Evidence per claim | `claim_id`, `sentence`, `sentence_source`, `confidence` |
| `relation_evidence` | Derived cache per canonical edge from support-claim evidence | `relation_id`, `evidence_sentence`, `evidence_tier` |
| `provenance` | Ingestion lineage | `source_type`, `source_ref`, `extraction_run_id` |

### 4.2 Existing API prefix

Research-space scoped routes are mounted under:

```
/research-spaces/{space_id}/...
```

Any new route examples in this RFC use that prefix.

### 4.3 Existing cross-space integrity pattern

`relations` already enforces same-space integrity with composite FKs (`source_id + research_space_id`, `target_id + research_space_id`) referencing `entities(id, research_space_id)`. This RFC applies the same pattern to new claim tables.

---

## 5. Core Design Decisions

1. **`claim_participants` is canonical structural truth for claims.**
2. **`metadata_payload.concept_refs` is extraction provenance/audit context, not retrieval truth.**
3. **Cross-space constraints must be DB-enforced**, not only app-enforced.
4. **One logical claim edge per `(space, source, type, target)`** in `claim_relations`; confirmations accumulate in provenance fields, not duplicate rows.
5. **Claim relation governance is explicit:** confidence + review status + provenance metadata.

### 5.1 SOLID/Clean Architecture conformance (explicit and required)

1. Layer ownership is mandatory:
   - Domain layer owns business entities and repository ports for this RFC (`src/domain/entities/kernel/`, `src/domain/repositories/kernel/`).
   - Application layer owns orchestration/use-cases (`src/application/services/` and agent services where relevant).
   - Infrastructure layer owns SQLAlchemy models, migrations, and repository adapters (`src/models/database/kernel/`, `src/infrastructure/repositories/kernel/`, `alembic/versions/`).
   - Presentation layer owns HTTP and UI composition only (`src/routes/research_spaces/`, `src/web/`).
2. Dependency direction is mandatory:
   - `routes -> application services -> domain ports -> infrastructure adapters`
   - prohibited: route handlers importing repositories/models directly.
   - prohibited: application services reaching into SQLAlchemy session/model internals directly.
3. Single Responsibility Principle is enforced:
   - route handlers remain thin request/response mappers.
   - business rules live in application/domain services, not in routes or UI actions.
   - persistence concerns live in repository implementations only.
4. Dependency Inversion Principle is enforced:
   - application services depend on repository interfaces (ports), not concrete SQLAlchemy repositories.
   - concrete bindings are wired only in dependency injection modules (`src/infrastructure/dependency_injection/`).
5. Interface segregation and typing are enforced:
   - create focused repository interfaces for participants and claim-relations instead of broad kitchen-sink repositories.
   - no `Any` in new domain/application code; use existing shared typed contracts (`src/type_definitions/`) and strict MyPy-compliant annotations.
6. Error boundary ownership is explicit:
   - domain/application raise typed domain errors.
   - presentation layer maps domain errors to HTTP responses.
7. Greenfield default applies:
   - no fallback paths, dual writes, or compatibility shims unless explicitly approved by maintainers.

---

## 6. Schema Changes

All changes are additive except a prerequisite unique constraint on `relation_claims` needed for composite FKs.

### 6.1 Prerequisite: composite FK target on `relation_claims`

Add unique key if not already present:

```sql
ALTER TABLE relation_claims
ADD CONSTRAINT uq_relation_claims_id_space
UNIQUE (id, research_space_id);
```

This enables composite references `(claim_id, research_space_id)` from child tables.

### 6.2 New table: `claim_participants`

```sql
CREATE TABLE claim_participants (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id          UUID NOT NULL,
    research_space_id UUID NOT NULL REFERENCES research_spaces(id) ON DELETE CASCADE,

    -- Label-first ingestion is supported; entity resolution can happen later.
    label             VARCHAR(512),
    entity_id         UUID,

    role              VARCHAR(32) NOT NULL,
    position          SMALLINT,
    qualifiers        JSONB NOT NULL DEFAULT '{}',

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_claim_participants_role CHECK (
        role IN ('SUBJECT', 'OBJECT', 'CONTEXT', 'QUALIFIER', 'MODIFIER')
    ),

    -- Must have at least one anchor: free-text label or resolved entity.
    CONSTRAINT ck_claim_participants_anchor CHECK (
        label IS NOT NULL OR entity_id IS NOT NULL
    ),

    -- Claim must belong to same space.
    CONSTRAINT fk_claim_participants_claim_space
        FOREIGN KEY (claim_id, research_space_id)
        REFERENCES relation_claims(id, research_space_id)
        ON DELETE CASCADE,

    -- Resolved entity must belong to same space.
    CONSTRAINT fk_claim_participants_entity_space
        FOREIGN KEY (entity_id, research_space_id)
        REFERENCES entities(id, research_space_id)
        ON DELETE SET NULL
);
```

Indexes:

```sql
CREATE INDEX idx_claim_participants_claim
    ON claim_participants(claim_id);

CREATE INDEX idx_claim_participants_space_entity
    ON claim_participants(research_space_id, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE INDEX idx_claim_participants_space_role
    ON claim_participants(research_space_id, role);
```

### 6.3 New table: `claim_relations`

```sql
CREATE TABLE claim_relations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_space_id UUID NOT NULL REFERENCES research_spaces(id) ON DELETE CASCADE,
    source_claim_id   UUID NOT NULL,
    target_claim_id   UUID NOT NULL,

    relation_type     VARCHAR(32) NOT NULL,

    -- Provenance + governance
    agent_run_id      VARCHAR(255),
    source_document_id UUID REFERENCES source_documents(id),
    confidence        FLOAT NOT NULL DEFAULT 0.5
                      CHECK (confidence >= 0.0 AND confidence <= 1.0),
    review_status     VARCHAR(32) NOT NULL DEFAULT 'PROPOSED'
                      CHECK (review_status IN ('PROPOSED', 'ACCEPTED', 'REJECTED')),
    evidence_summary  TEXT,
    metadata_payload  JSONB NOT NULL DEFAULT '{}',

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_claim_relations_type CHECK (
        relation_type IN (
            'SUPPORTS', 'CONTRADICTS', 'REFINES',
            'CAUSES', 'UPSTREAM_OF', 'DOWNSTREAM_OF',
            'SAME_AS', 'GENERALIZES', 'INSTANCE_OF'
        )
    ),
    CONSTRAINT ck_claim_relations_no_self_loop CHECK (source_claim_id <> target_claim_id),

    -- Both claim endpoints must belong to same space.
    CONSTRAINT fk_claim_relations_source_space
        FOREIGN KEY (source_claim_id, research_space_id)
        REFERENCES relation_claims(id, research_space_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_claim_relations_target_space
        FOREIGN KEY (target_claim_id, research_space_id)
        REFERENCES relation_claims(id, research_space_id)
        ON DELETE CASCADE,

    -- Prevent edge inflation from duplicates.
    CONSTRAINT uq_claim_relations_space_edge
        UNIQUE (research_space_id, source_claim_id, relation_type, target_claim_id)
);
```

Indexes:

```sql
CREATE INDEX idx_claim_relations_source
    ON claim_relations(source_claim_id);

CREATE INDEX idx_claim_relations_target
    ON claim_relations(target_claim_id);

CREATE INDEX idx_claim_relations_space_type
    ON claim_relations(research_space_id, relation_type);

CREATE INDEX idx_claim_relations_review_status
    ON claim_relations(review_status);
```

### 6.4 Row-Level Security

Enable RLS and force RLS for both new tables, following established kernel policies:

```sql
ALTER TABLE claim_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_participants FORCE ROW LEVEL SECURITY;

ALTER TABLE claim_relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_relations FORCE ROW LEVEL SECURITY;
```

Policy expression should match existing claim tables:

1. Allow when `app.bypass_rls = true`.
2. Allow when `app.is_admin = true`.
3. Otherwise restrict to spaces where current user is owner/member.
4. Apply same expression to both `USING` and `WITH CHECK`.

---

## 7. Source-of-Truth Contract: `claim_participants` vs `concept_refs`

To avoid dual structural truth:

1. `claim_participants` is canonical for retrieval, filtering, and traversal.
2. `metadata_payload.concept_refs` remains extraction provenance (concept set, member IDs, decision IDs, resolver metadata).
3. Extraction flow still writes `concept_refs`.
4. Resolver/write flow maps `concept_refs.source_member_id` / `concept_refs.target_member_id` into participant `entity_id` when resolution exists.
5. UI/search features read from `claim_participants` (not from raw metadata) once populated.

This keeps backward continuity while converging on one structural model.

---

## 8. Write Path Changes

### 8.1 Extraction claim write flow

After `relation_claims` insert:

1. Build SUBJECT/OBJECT participants from extracted claim endpoints.
2. Include optional CONTEXT/QUALIFIER/MODIFIER when emitted by extraction contract.
3. If an endpoint entity ID is known, write `entity_id`.
4. If unresolved, keep `entity_id = NULL` and preserve `label`.
5. Persist `concept_refs` in metadata for provenance continuity.

### 8.2 Manual hypothesis flow

Manual hypothesis claims still write to `relation_claims` (existing claim-first design).

Participant behavior:

1. If seed entity IDs are provided, write one or more SUBJECT participants with `entity_id`.
2. If only free text exists, write at least one participant with `label` so the anchor CHECK passes.

### 8.3 Claim relation creation flow

Whether generated by agent or manually curated, each `claim_relations` row must include:

1. `relation_type`.
2. `confidence`.
3. `review_status` defaulting to `PROPOSED`.
4. Provenance fields (`agent_run_id`, `source_document_id`, `metadata_payload`) when available.

---

## 9. Backfill Plan

### 9.1 Participants backfill for existing claims

For each existing `relation_claims` row:

1. Try to create SUBJECT from source endpoint.
2. Try to create OBJECT from target endpoint.
3. Source endpoint mapping order:
   - `metadata_payload.source_entity_id` (if valid + same space)
   - `metadata_payload.concept_refs.source_member_id` -> resolved entity (if available)
   - `source_label`
4. Target endpoint mapping order:
   - `metadata_payload.target_entity_id` (if valid + same space)
   - `metadata_payload.concept_refs.target_member_id` -> resolved entity (if available)
   - `target_label`
5. **Skip participant creation for an endpoint only when both label and entity are missing/unresolvable.**

This aligns with `ck_claim_participants_anchor` and avoids forcing synthetic labels.

### 9.2 Claim relations backfill

No mandatory backfill in V1. `claim_relations` starts empty and is populated by:

1. Curator actions.
2. Agent proposals (reviewed later).

---

## 10. API and Query Surface

### 10.1 New/updated routes

Use research-space prefix consistently:

1. `GET /research-spaces/{space_id}/claims/by-entity/{entity_id}`
2. `GET /research-spaces/{space_id}/claims/{claim_id}/participants` (optional convenience)
3. `POST /research-spaces/{space_id}/claim-relations`
4. `PATCH /research-spaces/{space_id}/claim-relations/{relation_id}` (review status)

### 10.2 Query examples

Entity -> claims:

```sql
SELECT rc.*, cp.role, cp.label, cp.entity_id
FROM claim_participants cp
JOIN relation_claims rc ON rc.id = cp.claim_id
WHERE cp.research_space_id = :space_id
  AND cp.entity_id = :entity_id
ORDER BY rc.created_at DESC;
```

Entity co-occurrence within claim:

```sql
SELECT DISTINCT rc.id
FROM relation_claims rc
JOIN claim_participants a ON a.claim_id = rc.id
JOIN claim_participants b ON b.claim_id = rc.id
WHERE rc.research_space_id = :space_id
  AND a.entity_id = :entity_a
  AND b.entity_id = :entity_b;
```

Claim chain traversal:

```sql
WITH RECURSIVE chain AS (
    SELECT
        cr.target_claim_id AS claim_id,
        1 AS depth,
        ARRAY[cr.source_claim_id]::uuid[] AS path
    FROM claim_relations cr
    JOIN claim_participants cp ON cp.claim_id = cr.source_claim_id
    WHERE cr.research_space_id = :space_id
      AND cp.entity_id = :start_entity_id
      AND cr.relation_type IN ('CAUSES', 'UPSTREAM_OF')

    UNION ALL

    SELECT
        cr.target_claim_id,
        chain.depth + 1,
        chain.path || cr.source_claim_id
    FROM claim_relations cr
    JOIN chain ON chain.claim_id = cr.source_claim_id
    WHERE cr.research_space_id = :space_id
      AND chain.depth < :max_depth
      AND NOT (cr.target_claim_id = ANY(chain.path))
)
SELECT claim_id, depth, path
FROM chain;
```

---

## 11. Frontend UX and Graph View Updates

### 11.1 Curation hypotheses card updates

Applies to `/research-spaces/{space_id}/curation` in the Next.js curation surface.

1. Keep one hypotheses card with unified data source: `relation_claims` filtered by `polarity='HYPOTHESIS'`.
2. Expose two actions with clear semantics:
   - `Log hypothesis` (manual create)
   - `Auto-generate from graph` (agent generation), gated by `GRAPH_ENABLE_HYPOTHESIS_GENERATION`
3. Inputs:
   - `Hypothesis statement` (required for manual)
   - `Rationale` (required for manual)
   - `Seed entity IDs` (optional, comma/whitespace separated)
4. List behavior:
   - Default sort `created_at desc`
   - Filters: `origin`, `status`, `certainty`
   - Show provenance badges from metadata (`manual`, `graph_agent`, other known origins)
5. Triage behavior:
   - Quick actions call existing claim status endpoint (`OPEN`, `NEEDS_MAPPING`, `REJECTED`, `RESOLVED`)
   - No direct canonical relation writes from this card
6. Loading and error behavior:
   - Buttons show loading labels while requests run
   - Auto-generate and manual actions always render user-visible result messages (success, no-op, error)
   - No silent failures

### 11.2 User-visible messaging contract (required)

Auto-generation must return explanatory feedback when zero hypotheses are created.

1. `no_seed_entities_resolved`: no usable seed entities in this space.
2. `no_candidates_discovered`: graph exploration found no candidate relations.
3. `all_candidates_below_threshold`: candidates were scored but none met minimum threshold.
4. `all_candidates_deduped`: all candidates already exist as active hypothesis claims.
5. `no_candidates_selected`: candidates existed but none survived selection constraints.

UI must show:

1. Top-level summary (for example, `Generation completed but produced no new hypotheses.`).
2. One or more reason lines mapped from error codes.
3. Retry affordance (`Refresh hypotheses` and/or rerun with explicit seeds).

### 11.3 Graph view updates (required)

Yes, graph view should change to reflect the overlay model while keeping canonical relations stable by default.

1. Add view mode switch:
   - `Canonical Graph` (existing relations view, default)
   - `Claim Overlay` (claim and claim-relation topology)
2. `Canonical Graph` mode remains unchanged as the default curation/traversal surface for `relations`.
3. `Claim Overlay` mode behavior:
   - Render claim nodes (`relation_claims`) and claim-to-claim edges (`claim_relations`)
   - Surface participant context (`claim_participants`) in node side panel
   - Show relation edge metadata (`relation_type`, `confidence`, `review_status`, provenance)
4. Cross-linking behavior:
   - Selecting a canonical relation shows linked supporting/refuting claims
   - Selecting a claim can highlight a linked canonical relation when `linked_relation_id` exists, but canonical explainability must come from `relation_projection_sources`, not that pointer
5. Empty state behavior:
   - If no `claim_relations` exist, show explicit empty state with CTA to create/review links
6. Safety:
   - Graph view actions in claim overlay must not mutate canonical `relations` unless explicit separate curator action is taken

---

## 12. Implementation Plan

### Phase 1: Integrity-first schema foundation

1. Add unique constraint `uq_relation_claims_id_space`.
2. Add `claim_participants` table + indexes + RLS.
3. Add `claim_relations` table + indexes + RLS.
4. Add domain entities + repository ports, infrastructure SQLAlchemy models + repository implementations, and DI bindings (respecting Section 5.1 dependency direction).
5. Add migration tests for constraint behavior.

### Phase 2: Write path and source-of-truth alignment

1. Update extraction write flow to populate `claim_participants`.
2. Keep writing `metadata_payload.concept_refs` as provenance.
3. Update manual hypothesis flow to write participants.
4. Add API read endpoints backed by participants.
5. Keep route handlers thin and service-driven; no direct route-to-repository coupling.

### Phase 3: Backfill and retrieval migration

1. Backfill existing claims into participants with skip rules for missing anchors.
2. Shift search/UI retrieval from metadata parsing to participant joins.
3. Add monitoring for unresolved participant rates.

### Phase 4: Claim relation governance and UI

1. Enable curator create/review for claim-to-claim edges.
2. Add review state transitions (`PROPOSED` -> `ACCEPTED`/`REJECTED`).
3. Deliver hypotheses card UX contract from Section 11.1 and 11.2.
4. Add contradiction/mechanism views driven by persisted edges.
5. Add graph mode switch and claim overlay behavior from Section 11.3.

### 12.1 Step-by-step progressive rollout gates

Each phase is gated. The next phase does not start until the current gate passes.

1. Gate A (after Phase 1):
   - migrations apply cleanly on a fresh DB and existing dev DB
   - composite FK constraints are enforced in integration tests
   - duplicate claim-relation edge insert is rejected by DB
2. Gate B (after Phase 2):
   - extraction and manual hypothesis flows persist valid participant rows
   - API responses for claim retrieval by entity use participant joins
   - no canonical `relations` writes introduced by new endpoints
3. Gate C (after Phase 3):
   - participant backfill is idempotent
   - unresolved participant rate dashboard is available
   - historical claims remain queryable in curation without UI regressions
4. Gate D (after Phase 4):
   - hypotheses card UX contract passes frontend tests
   - graph mode switch and claim overlay flows pass integration/e2e checks
   - staging sign-off from curation users before production rollout

### 12.2 Testing plan

1. Unit tests:
   - participant payload mapping from extraction/manual flows
   - claim relation validation (`no self loop`, relation type whitelist, confidence bounds)
   - reason-code mapping for zero-result hypothesis generation messaging
2. Repository/integration tests:
   - composite FK same-space enforcement on `claim_participants` and `claim_relations`
   - unique edge constraint on `claim_relations`
   - RLS policy behavior for member, non-member, admin, and bypass contexts
   - backfill behavior with missing labels, missing entity IDs, and concept-ref resolution
3. API tests:
   - `GET /research-spaces/{space_id}/claims/by-entity/{entity_id}`
   - `POST /research-spaces/{space_id}/claim-relations`
   - `PATCH /research-spaces/{space_id}/claim-relations/{relation_id}`
   - auth/membership denial cases for all new routes
4. Frontend tests:
   - hypotheses card button visibility under `GRAPH_ENABLE_HYPOTHESIS_GENERATION`
   - loading, success, no-op, and error states for manual and auto-generate actions
   - filter behavior (`origin`, `status`, `certainty`) and triage quick actions
   - user-visible diagnostic messages for each zero-result error code
5. End-to-end checks:
   - curator creates hypothesis, sees it, triages it, and verifies state transitions
   - claim overlay mode renders claims/edges and preserves canonical graph mode behavior
6. Architecture conformance checks:
   - layering/dependency validation script passes (`scripts/validate_architecture.py`)
   - no forbidden imports (`routes` -> repository/model, application -> SQLAlchemy internals)
   - strict typing gates pass (`make type-check`, no new `Any` usage)

### 12.3 Regression checks (required before merge)

1. Existing extraction claim list and triage flows continue to work unchanged.
2. Existing concept decision routes and audit logging remain unchanged.
3. Canonical graph endpoints and `relations` visualization remain stable in default mode.
4. No unexpected writes to canonical `relations` from hypothesis/card/overlay actions.
5. Existing hypothesis manual logging behavior remains backward compatible.
6. `make all` (or equivalent CI suite) passes with new tests included.
7. Architecture validation and dependency checks remain green after all RFC changes.
8. DI wiring stays centralized in infrastructure DI modules with no ad hoc service construction in routes.

---

## 13. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Cross-space row mismatch from denormalized IDs | RLS bypass and data leakage risk | Composite FKs on both new tables referencing `(id, research_space_id)` |
| Duplicate edge inflation in claim graph | Distorted traversal counts and ranking | Unique edge constraint on `claim_relations` |
| Dual structural truth (`concept_refs` vs participants) | Query inconsistency and drift | Explicit contract: participants canonical, metadata provenance-only |
| Sparse endpoint data in historical claims | Partial participant rows | Anchor CHECK + backfill skip rules + progressive resolution |
| Agent-generated links lack governance | Low trust and review ambiguity | `confidence`, `review_status`, provenance fields, audit trails |

---

## 14. Success Criteria

1. DB rejects any participant or claim-relation row that violates same-space integrity.
2. DB rejects duplicate `(space, source_claim, relation_type, target_claim)` edges.
3. Claim retrieval by entity uses `claim_participants` and does not require metadata JSON parsing for core joins.
4. Backfill completes without synthetic placeholder labels and without constraint violations.
5. Claim-to-claim edges carry provenance, confidence, and review status fields at creation.
6. All new route examples and docs consistently use `/research-spaces/{space_id}/...`.
7. Hypotheses card actions always return visible user feedback, including zero-result auto-generation reasons.
8. Auto-generate button visibility is correctly gated by `GRAPH_ENABLE_HYPOTHESIS_GENERATION`.
9. Curators can triage hypothesis claims from the card using existing claim status transitions.
10. Graph view supports both `Canonical Graph` and `Claim Overlay` without implicit canonical writes.
11. Progressive rollout gates (A through D in Section 12.1) are satisfied in order.
12. Regression checks in Section 12.3 pass before merge.
13. CI quality gate (`make all` or equivalent) passes with new test coverage.
14. SOLID/Clean-Architecture rules in Section 5.1 are satisfied and verified by architecture tests/lint checks.

---

## 15. Compatibility Notes

1. Existing `relation_claims` reads/writes remain valid.
2. Existing metadata (`concept_refs`) remains intact for audit continuity.
3. `linked_relation_id` remains as a compatibility/read-model pointer for navigation and UI joins, not as authoritative projection lineage.
4. Public canonical relation creation is deprecated; internal `POST /relations` remains a temporary admin/system compatibility path that still creates a manual support claim and materializes through the projection service.

---

## 16. Open Questions

1. Should `claim_relations.relation_type` move to dictionary governance in V2, or remain enum-constrained until scale demands flexibility?
2. When global readiness remains clean, should the internal compatibility `POST /relations` route be removed entirely or retained as a break-glass admin workflow?
3. Which review queue UX best balances throughput vs precision for `PROPOSED` claim-to-claim links?
