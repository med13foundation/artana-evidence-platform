# Graph Use Cases

## 1. Ingest a paper and materialize claim-backed relations

Actors:

- source ingestion
- enrichment
- extraction
- relation projection materializer

Flow:

1. A source document is ingested and optionally enriched.
2. Extraction creates observations and relation claims.
3. Structured claim participants are written.
4. Claim evidence is written.
5. Resolved support claims materialize canonical relations.
6. The canonical graph becomes available for browsing and search.

Outcome:

- claims remain the authoritative ledger
- canonical graph updates remain explainable

## 2. Curate a support claim into the canonical graph

Actors:

- curator
- relation-claim triage route
- projection materializer

Flow:

1. A curator reviews an open support claim.
2. The claim is moved to `RESOLVED` and remains `PERSISTABLE`.
3. The materializer creates or reuses a canonical relation.
4. Projection lineage is recorded.
5. Derived canonical evidence is refreshed.

Outcome:

- canonical relation is visible in default graph reads

## 3. Record disagreement without creating a canonical relation

Actors:

- curator or extraction pipeline
- claim ledger

Flow:

1. A `REFUTE`, `UNCERTAIN`, or `HYPOTHESIS` claim is created.
2. The claim may point at an existing canonical relation through `linked_relation_id`.
3. No canonical relation is created from that claim.

Outcome:

- disagreement is preserved in claim space
- canonical graph stays support-projection-only

## 4. Browse the canonical graph

Actors:

- researcher
- canonical graph endpoints

Flow:

1. The user requests relation lists, neighborhood graph, graph export, or graph document.
2. The repository returns claim-backed projected relations only.
3. The UI can inspect linked claims and evidence from the returned graph data.

Outcome:

- default graph view stays stable and explainable

## 5. Inspect the claim overlay

Actors:

- curator
- claim graph endpoints

Flow:

1. The user loads claims by entity, participants, claim relations, or claim evidence.
2. The user inspects support/refute context around a canonical relation.
3. `linked_relation_id` can still be used for navigation, but projection lineage remains the explainability source.

Outcome:

- richer scientific disagreement and mechanism modeling without changing canonical truth

## 6. Build one graph document for UI rendering

Actors:

- graph document route
- relation service
- relation claim service
- projection source service

Flow:

1. The user requests `POST /graph/document`.
2. Canonical relations are gathered first.
3. Projection-linked claims are gathered for explainability.
4. Linked-only claims may still appear in compatibility metadata.
5. Evidence nodes and participant edges are added.

Outcome:

- the UI gets one unified payload for canonical, claim, and evidence layers

## 7. Search the graph in natural language

Actors:

- researcher
- graph search service

Flow:

1. The user asks a natural-language question.
2. The graph search service queries the claim-backed canonical graph.
3. Evidence and provenance are returned with the search result.

Outcome:

- search stays grounded in explainable canonical projections

## 8. Repair and validate rollout readiness

Actors:

- operator
- readiness service
- participant backfill service

Flow:

1. Run `make graph-readiness`.
2. Audit for:
   - orphan relations
   - missing support participants
   - missing support claim evidence
   - linked relation mismatches
   - invalid projection relations
3. Run repair where appropriate.
4. Re-audit until all counts are zero.

Outcome:

- graph rollout is considered complete only when unresolved cases are zero globally

## 9. Inspect one domain view

Actors:

- researcher
- graph view route

Flow:

1. The user requests a pack-owned view type such as `gene`, `paper`, `team`,
   or `report`.
2. The route loads the focal resource.
3. Related claims, claim-to-claim edges, participants, and claim evidence are assembled.
4. Claim-backed canonical relations are included where they exist.

Outcome:

- the UI and agents get one domain-specific, explainable graph bundle without creating a second truth model

## 10. Traverse a mechanism chain

Actors:

- researcher or AI agent
- claim graph

Flow:

1. The user starts from one root claim.
2. The system traverses mechanism-style `claim_relations` such as `CAUSES` and `UPSTREAM_OF`.
3. Claims, participants, evidence, and linked canonical relations are returned together.

Outcome:

- mechanism exploration stays claim-backed, reviewable, and evidence-linked

## 11. Persist reusable mechanism paths

Actors:

- operator or scheduled job
- reasoning path service

Flow:

1. Run the reasoning-path rebuild for one research space or globally.
2. The service scans grounded support claims and accepted claim relations.
3. Simple mechanism paths are persisted as derived read models.
4. Path rows remain explainable by ordered claims and claim relations.

Outcome:

- mechanism exploration becomes reusable
- AI agents do not have to rediscover the same grounded chain every time

## 12. Generate a hypothesis from a stored path

Actors:

- researcher or AI agent
- hypothesis generation service

Flow:

1. The user requests hypothesis generation.
2. Active reasoning paths are checked first.
3. The service creates `relation_claims` with `polarity=HYPOTHESIS`.
4. Structured participants use the path start and end entities.
5. Hypothesis metadata records the source reasoning path and supporting claim IDs.

Outcome:

- suggestion stays claim-first
- the path remains a derived reasoning artifact, not new truth

## 13. Transfer a mechanism from nearby biology into a reviewable hypothesis

Actors:

- researcher or AI agent
- hypothesis generation service
- reasoning path service

## 14. Switch the same runtime onto a different built-in pack

Actors:

- operator
- graph service startup/runtime

Flow:

1. The operator sets `GRAPH_DOMAIN_PACK` to `biomedical` or `sports`.
2. Startup bootstraps the built-in packs and resolves the active one.
3. Runtime identity, graph views, connector defaults, dictionary seeding,
   auth/tenancy-neutral behavior, and read-model framework continue unchanged.
4. Pack-owned behavior changes without requiring core forks or API contract
   rewrites.

Outcome:

- one graph-core runtime supports multiple domains through explicit pack-owned
  extension points
- claim ledger

Flow:

1. The user requests hypothesis generation for a focal entity such as `MED13`.
2. The service loads direct active reasoning paths from that entity.
3. The service loads nearby canonical neighbors such as related genes or pathways.
4. Nearby support claims with usable evidence are compared for compatible mechanism or phenotype patterns.
5. Contradictory nearby `REFUTE` or `UNCERTAIN` claims reduce the transfer score.
6. If the score is strong enough, the system creates one `HYPOTHESIS` claim with explicit transfer metadata.

Outcome:

- nearby biology helps generate a candidate mechanism hypothesis
- direct support and transferred support remain separated in metadata
- the result stays claim-only and reviewable
