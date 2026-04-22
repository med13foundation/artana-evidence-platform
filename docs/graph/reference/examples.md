# Graph Examples

## 1. Support claim materializes a canonical relation

### Claim-side state

```text
Claim:
  polarity=SUPPORT
  claim_status=RESOLVED
  persistability=PERSISTABLE

Participants:
  SUBJECT -> MED13
  OBJECT  -> Cardiomyopathy

Evidence:
  "MED13 variants were associated with cardiomyopathy."
```

### Materialized result

```text
relation_claims
  -> source claim row

relation_projection_sources
  -> relation_id = rel-123
  -> claim_id = claim-456

relations
  -> rel-123
  -> source = MED13
  -> type = ASSOCIATED_WITH
  -> target = Cardiomyopathy

relation_evidence
  -> derived from claim_evidence for claim-456
```

## 2. Refute claim stays claim-only

```text
Claim:
  polarity=REFUTE
  claim_status=RESOLVED
  persistability=PERSISTABLE
```

Allowed behavior:

- may link to an existing canonical relation through `linked_relation_id`
- does not create `relation_projection_sources`
- does not create a canonical relation

## 3. Graph-document edge metadata

A canonical graph-document edge can expose both authoritative and compatibility
claim references.

Example shape:

```json
{
  "kind": "CANONICAL_RELATION",
  "canonical_relation_id": "rel-123",
  "metadata": {
    "support_claim_count": 1,
    "refute_claim_count": 1,
    "projection_claim_ids": ["claim-support-1"],
    "linked_claim_ids": ["claim-support-1", "claim-refute-9"],
    "explainable_by_projection": true
  }
}
```

Interpretation:

- `projection_claim_ids` are the authoritative explainability set
- `linked_claim_ids` are broader UI/navigation context

## 4. Internal compatibility relation creation

`POST /relations` is still implemented, but the route is internal-only.

Behavior:

1. create a manual support claim
2. create structured participants
3. create claim evidence if provided
4. materialize through the projection service

This preserves the claim-first contract even for compatibility workflows.

## 5. Readiness output

Example clean result:

```text
ready=True
orphan_relations=0
missing_claim_participants=0
missing_claim_evidence=0
linked_relation_mismatches=0
invalid_projection_relations=0
```

Example unresolved interpretation:

- `orphan_relations > 0`
  canonical graph contains unexplained edges
- `missing_claim_participants > 0`
  support claims cannot be projected safely
- `missing_claim_evidence > 0`
  support projections cannot be explained fully
- `linked_relation_mismatches > 0`
  compatibility pointers drifted from authoritative lineage
- `invalid_projection_relations > 0`
  canonical relations have projection rows but no valid support source

## 6. Mechanism chain example

```text
Claim A: MED13 mutation disrupts mediator complex function
   CAUSES
Claim B: Mediator complex dysfunction perturbs transcription
   UPSTREAM_OF
Claim C: Transcription dysregulation contributes to neurodevelopmental disease
```

Mechanism-chain response includes:

- root claim
- traversed claims
- mechanism-style claim edges
- participants
- evidence
- any linked canonical relations already materialized from support claims

## 7. Gene view example

Example request:

```text
GET /v1/spaces/{space_id}/graph/views/gene/{entity_id}
```

Typical response contents:

- focal `GENE` entity
- canonical relations touching that gene
- claims mentioning the gene through `claim_participants`
- claim-to-claim edges for overlay and mechanism context
- claim evidence rows for those claims

## 8. Sports match view example

Example request:

```text
GET /v1/spaces/{space_id}/graph/views/match/{entity_id}
```

Typical response contents under `GRAPH_DOMAIN_PACK=sports`:

- focal `MATCH` entity
- canonical relations touching that match
- claims mentioning the match, teams, or athletes through `claim_participants`
- claim-to-claim edges for competition context
- claim evidence rows drawn from match reports or related records

## 9. Paper view example

Example request:

```text
GET /v1/spaces/{space_id}/graph/views/paper/{source_document_id}
```

Typical response contents:

- focal source document
- claims extracted from that paper
- structured participants for those claims
- claim evidence rows from that paper
- any claim-backed canonical relations materialized from those claims

## 10. Persisted reasoning path example

```text
Claim A: MED13 is part of the mediator complex
   CAUSES
Claim B: Mediator dysfunction is associated with speech delay
```

Derived path:

```text
reasoning_paths
  -> start_entity = MED13
  -> end_entity = Speech delay
  -> path_kind = MECHANISM
  -> status = ACTIVE
  -> confidence = 0.73

reasoning_path_steps
  -> step 0
  -> source_claim_id = Claim A
  -> target_claim_id = Claim B
  -> claim_relation_id = edge-1
```

Interpretation:

- the path is derived from reviewed claim-space edges
- it is reusable for search, explanation, and hypothesis suggestion
- it is not canonical truth

## 11. Path-backed hypothesis example

Generated hypothesis metadata can now look like:

```json
{
  "origin": "reasoning_path",
  "reasoning_path_id": "path-123",
  "start_entity_id": "entity-med13",
  "end_entity_id": "entity-speech-delay",
  "supporting_claim_ids": ["claim-a", "claim-b"],
  "path_confidence": 0.73,
  "path_length": 1
}
```

Interpretation:

- the hypothesis is still a `relation_claim`
- the supporting path is explicit
- the reasoning artifact remains rebuildable from claims

## 12. Transfer-backed mechanism hypothesis example

Generated hypothesis metadata can also combine direct seed support with nearby
biology:

```json
{
  "origin": "mechanism_transfer",
  "reasoning_path_id": "path-med13-speech-delay",
  "start_entity_id": "entity-med13",
  "end_entity_id": "entity-speech-delay",
  "direct_supporting_claim_ids": ["claim-med13-a", "claim-med13-b"],
  "transferred_supporting_claim_ids": ["claim-med12-1", "claim-med16-4"],
  "transferred_from_entities": ["entity-med12", "entity-med16"],
  "transfer_basis": [
    "neighbor_via_part_of",
    "relation_family_overlap",
    "shared_end_entity"
  ],
  "contradiction_claim_ids": [],
  "path_confidence": 0.74,
  "candidate_score": 0.81,
  "explanation": "MED13 may connect to Speech delay based on direct reasoning-path claims and nearby Mediator-gene support."
}
```

Interpretation:

- the hypothesis is still a `relation_claim`
- direct MED13 support and transferred nearby support stay separate
- contradiction signals remain visible in metadata
- no canonical relation is created automatically from the transfer
