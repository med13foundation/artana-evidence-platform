# V2 Reusable Graph Engine Plan

## Purpose

This plan describes how to evolve `services/artana_evidence_db` from a
standalone biomedical graph service into a reusable graph database engine that
can serve many domains through domain dictionary packs.

The goal is simple:

```text
artana_evidence_db
  = reusable graph engine, official rulebook, validation, persistence

artana_evidence_api
  = optional AI layer that discovers, reasons, proposes, and asks for approval

domain packs
  = vocabulary and rules for biomedical, sports, legal, business, or custom use
```

The graph database service must be useful by itself. A project should be able
to run only `artana_evidence_db`, load a domain pack, create graph spaces,
manage the dictionary, add entities, add claims/evidence, validate relations,
promote approved claims, search/export the graph, and operate the database
without depending on `services/artana_evidence_api`.

## Product Principles

### The DB Service Is The Rulebook

`artana_evidence_db` owns official graph state:

- graph spaces and memberships
- entities and entity identifiers
- observations
- claims and claim evidence
- canonical relations
- provenance
- dictionary state
- concept governance
- relation constraints
- projection from claim state to canonical graph state
- read models and repair/rebuild operations

The DB service decides whether a write is valid. It must return clear reasons
when a write is invalid or needs review.

### AI Proposes, The DB Decides

`artana_evidence_api` may use Artana Kernel and models to find missing entities,
new relation types, better constraints, candidate claims, and hypotheses.

It should not silently make official graph rules.

Allowed AI outputs:

- candidate entity
- candidate relation
- candidate claim
- dictionary proposal
- concept proposal
- hypothesis
- rationale and evidence

Official DB outputs:

- approved entity type
- approved relation type
- approved relation constraint
- persisted claim
- promoted canonical relation
- approved concept decision

### Domain Packs Teach The Engine A Vocabulary

The core engine should not know that every deployment is biomedical.

A domain pack supplies:

- domain contexts
- entity types
- relation types
- relation synonyms
- relation constraints
- variable definitions
- qualifier definitions
- default source-type mappings
- view configuration
- deterministic pack-owned defaults

Example:

```text
GRAPH_DOMAIN_PACK=biomedical
  entity types: GENE, VARIANT, DISEASE, DRUG, PUBLICATION
  relation types: ASSOCIATED_WITH, CAUSES, TREATS, TARGETS

GRAPH_DOMAIN_PACK=sports
  entity types: TEAM, PLAYER, MATCH, SEASON, LEAGUE
  relation types: PLAYS_FOR, SCORED_IN, WON_AGAINST
```

Same engine, different rule pack.

## Product Operating Modes And Human Scenarios

The reusable graph DB should support more than one way of working. Different
projects want different levels of human control and AI autonomy. The engine
should make those modes explicit instead of hiding them inside one workflow.

The main product question is:

```text
Who is deciding truth right now?

human only
human with AI help
human approves evidence while AI manages graph details
AI manages graph updates under DB policy
AI manages evidence and graph updates under DB policy
```

### Mode 1: Manual / Human Curator

The human controls every important change.

Example:

```text
A curator reads a paper and approves:
MED13 ASSOCIATED_WITH developmental delay
```

The system may help validate, but the human approves the evidence, the claim,
and any official graph change.

Useful for:

- biomedical curation
- legal or regulated domains
- early trust-building
- sensitive projects where every change must be human-reviewed

Current support:

- mostly supported through claim creation, evidence attachment, triage,
  promotion, dictionary governance, and proposal review APIs.

### Mode 2: AI Assist, Human Batch Approval

AI prepares a package of proposed changes, and a human approves or rejects the
batch.

Example:

```text
AI finds 47 candidate facts from 12 papers.
Human sees:
  35 low-risk claims
  8 need review
  4 conflict with existing graph
Human approves a selected batch.
```

Useful for:

- literature review
- sports/stat updates
- business intelligence refreshes
- continuous monitoring with human checkpoints

Current support:

- partially supported through proposal ledgers, graph-change proposals, run
  artifacts, and review workflows.
- still needs a polished batch-review API and UI/API contract that groups
  concept, dictionary, claim, and evidence proposals into one review packet.

### Mode 3: Human Approves Evidence, AI Manages Graph

This is a key target mode. The user thinks only about evidence quality, not
graph mechanics.

Example:

```text
User approves evidence:
"A is related to B."

AI handles:
  Does A already exist?
  Does B already exist?
  Is this a synonym?
  Is this relation type allowed?
  Is a new concept proposal needed?
  Is a relation constraint proposal needed?
  Can the claim be promoted?
```

The human does not have to understand dictionary types, concept merges,
synonym collisions, or relation constraints. The DB still checks all rules.

Useful for:

- researchers who want to validate evidence but not manage ontology details
- nontechnical domain experts
- teams with a graph stewarding backlog
- reusable projects where the graph should remain clean without manual graph
  administration for every claim

Current support:

- partially supported. Phase 9 added concept proposals, graph-change
  proposals, connector proposals, AI decision envelopes, policy checks, and
  cross-space safety.
- the smooth end-to-end workflow is still pending: an evidence approval should
  trigger validation, graph repair/proposal generation, policy decisions, and
  final claim promotion through one orchestrated DB-owned path.

### Mode 4: AI Full Graph Mode

AI can propose and apply graph changes when DB policy allows it.

Example:

```text
AI proposes:
  concept: developmental delay
  synonym: DD
  relation: MED13 ASSOCIATED_WITH developmental delay

AI submits decision:
  APPLY_RESOLUTION_PLAN

DB checks:
  trusted AI principal
  confidence
  risk tier
  proposal hash
  evidence
  relation constraints
  same graph space
```

Useful for:

- low-risk exact ontology matches
- repetitive graph cleanup
- high-volume projects where review should focus on exceptions
- future AI-native graph operations

Current support:

- supported as Phase 9 building blocks through AI Full Mode APIs and policy.
- still needs more real workflow integration so Artana-powered runs choose and
  exercise these APIs during production tasks.

### Mode 5: AI Full Evidence Mode

AI can also decide evidence quality, not only graph structure.

Example:

```text
AI reads a source.
AI extracts a claim.
AI judges the evidence quality.
AI creates or resolves concepts.
AI creates the claim and evidence.
AI promotes the claim if policy allows.
```

Useful for:

- autonomous research agents
- always-on monitoring
- domains with low-risk evidence standards
- projects betting on AI as the primary decision-maker

Current support:

- not complete as a single product mode.
- claim evidence tables and AI provenance exist.
- DB-owned AI Full Mode can govern graph changes.
- a first-class evidence decision ledger and policy path are still needed so
  evidence review itself can be AI-managed, auditable, replay-safe, and
  reversible where possible.

### Mode 6: Conflict Resolution

The graph finds disagreement and asks for a decision.

Example:

```text
Source 1 says A increases B.
Source 2 says A decreases B.

System asks:
  keep both as context-specific
  prefer source 1
  prefer source 2
  mark conflict unresolved
  request more evidence
```

Useful for:

- science
- policy research
- legal precedent
- market intelligence

Current support:

- partially supported through duplicate/conflict validation, claim status, and
  relation conflict reads.
- still needs a first-class conflict-resolution proposal and decision workflow.

### Mode 7: Dictionary / Ontology Steward

The user manages the language of the graph.

Example:

```text
AI asks:
Should SENSITIZES_TO become an official relation type?
Should GENE SENSITIZES_TO DRUG be an allowed constraint?
```

Useful for:

- admins
- data architects
- domain experts
- teams building reusable domain packs

Current support:

- supported through dictionary proposal APIs, approval/reject/merge flows,
  changelog, and domain packs.

### Mode 8: Connector Review

AI proposes how a new source should map into the graph.

Example:

```text
CSV columns:
  gene, variant, phenotype, evidence_sentence

AI proposes:
  gene -> entity type GENE
  variant -> entity type VARIANT
  phenotype -> entity type PHENOTYPE
  evidence_sentence -> claim evidence sentence
```

Useful for:

- dataset imports
- labs with custom spreadsheets
- enterprise data integration
- reusable ingestion setup

Current support:

- Phase 9 supports connector metadata proposals.
- connector execution remains outside the DB service by design.
- still needs deeper mapping validation and an external connector runtime
  handshake.

### Mode 9: Research Assistant

The human asks questions and gets evidence-backed graph answers.

Example:

```text
What is the strongest evidence connecting MED13 to congenital heart disease?
```

Useful for:

- scientists
- analysts
- students
- executives and product teams

Current support:

- graph reads live in the DB.
- LLM narrative answers should live in `artana_evidence_api`.
- the DB should continue exposing deterministic graph documents, evidence
  bundles, reasoning paths, and provenance.

### Mode 10: Continuous Learning

The system keeps the graph fresh over time.

Example:

```text
Every week:
  check new papers
  check new records
  detect contradictions
  stage proposals
  auto-apply low-risk updates if policy allows
  send a summary to humans
```

Useful for:

- living knowledge bases
- biomedical monitoring
- competitive intelligence
- sports roster/stat updates

Current support:

- mostly AI-service side today.
- DB support exists through validation, proposal, graph-change, and AI decision
  APIs.
- still needs a clean DB-owned summary of what changed, why it changed, and
  what remains pending.

### Mode 11: Audit, Tutor, And Bootstrap

Audit mode answers:

```text
Why did AI add this relation?
Who or what approved it?
What evidence and policy allowed it?
```

Tutor mode explains:

```text
Why is this relation not allowed?
Why is this synonym risky?
What is missing before promotion?
```

Bootstrap mode starts a new project:

```text
Build a starter graph for MED13 heart disease evidence.
```

Useful for:

- compliance
- debugging AI decisions
- onboarding new users
- starting new domain projects quickly

Current support:

- auditability exists through provenance, changelog, proposal hashes, AI
  decisions, and graph read APIs.
- tutor/bootstrap experiences should be implemented in AI applications, but
  must rely on DB-owned validation explanations and policy traces.

### Priority Order

The next product phases should prioritize:

1. Human approves evidence, AI manages graph.
2. AI suggests, human batch approves.
3. AI Full Evidence Mode.
4. Audit / Why did AI do this?
5. Conflict resolution workflow.

## Current Gaps

### Gap 1: Biomedical Is Still Too Glued Into The DB Service

The code has a domain-pack-shaped model, but the active runtime is still mostly
biomedical.

Current symptoms:

- `services/artana_evidence_db/runtime/biomedical_pack.py` returns
  `BIOMEDICAL_GRAPH_DOMAIN_PACK` directly.
- `services/artana_evidence_db/graph_domain_config.py` contains large
  biomedical dictionaries and defaults.
- `services/artana_evidence_db/app.py` seeds biomedical starter concepts during
  service startup.
- Some composition code imports graph-domain config directly instead of
  resolving the active pack through a pack registry.

Target:

- Pack loading is explicit.
- `GRAPH_DOMAIN_PACK` selects an active pack.
- Biomedical is one pack, not the engine's identity.
- A second minimal pack proves that the boundary is real.

### Gap 2: AI Runtime Concerns Leak Into The DB Service

The reusable DB service should not own LLM prompts or model orchestration.

Current symptoms:

- biomedical prompts are packaged under `services/artana_evidence_db/runtime`.
- domain pack contracts include prompt and extraction fallback behavior.
- graph search and graph connection prompts are mixed with DB runtime config.

Target:

- Artana Kernel and model prompts live in `services/artana_evidence_api`.
- The DB service exposes deterministic graph APIs and validation APIs.
- The DB service can store model-authored evidence/provenance, but it does not
  run model reasoning.
- If the DB service stores embeddings, it owns storage and readiness, while the
  AI service owns model calls that produce embedding vectors.

### Gap 3: Dictionary Changes Need A Proposal Workflow

AI may correctly notice that the current dictionary lacks a good relation type.
That is useful and should be supported.

The problem is hidden official mutation. If AI discovers `SENSITIZES_TO`, it
should not quietly create an approved relation type and approved constraint as a
side effect of creating a claim.

Target:

```text
AI detects missing vocabulary
  -> creates dictionary proposal
  -> DB validates and stores proposal
  -> curator/admin approves, rejects, or merges
  -> approved proposal updates official dictionary
```

Needed proposal types:

- entity type proposal
- relation type proposal
- relation constraint proposal
- variable proposal
- value-set proposal
- concept proposal
- qualifier proposal

### Gap 4: Validation Needs First-Class APIs

AI services and external projects need to ask the DB:

```text
Would this entity be valid?
Would this observation be valid?
Would this triple be valid?
Would this claim be valid?
What is missing?
What should I do next?
```

Target:

- validation endpoints are side-effect free.
- validation and write endpoints use the same underlying validator.
- validation responses include stable error codes and suggested next actions.

### Gap 5: Startup Seeding Is Not Pack-Versioned

Current startup seeding is convenient, but not ideal for a reusable product.

Target:

- seeding is pack-driven.
- pack version is tracked.
- each graph space records the pack and pack version used for starter content.
- startup does not blindly mutate all existing spaces.
- admin APIs can run or repair seed state explicitly.

### Gap 6: Test Coverage Needs To Prove Reuse

Existing tests cover many graph-service behaviors, but V2 needs tests that prove
the service is reusable and stable across domains.

Target:

- tests run the same graph engine with at least two packs.
- tests prove AI services can only propose through governed APIs.
- tests prove official dictionary state changes only through approved flows.
- regression tests lock down previous boundary leaks.

### Gap 7: Product Modes Are Not Yet First-Class Workflows

The DB now exposes many of the primitives needed for different operating
modes, but the modes themselves are not yet first-class product workflows.

Current symptoms:

- a user can approve evidence or claims, but there is not yet one smooth
  evidence-to-graph orchestration path where AI handles missing concepts,
  synonyms, relation constraints, and claim promotion behind the scenes.
- AI Full Mode can govern concept and graph-change proposals, but existing
  AI-service workflows must intentionally load and use those tools.
- batch review exists as pieces, not as one reusable DB contract for mixed
  concept, dictionary, claim, evidence, and connector proposals.
- AI evidence decisions do not yet have the same first-class decision ledger as
  graph-change decisions.
- conflict resolution exists as validation and reads, not as a complete
  decision workflow.

Target:

- every graph space declares an operating mode.
- evidence approval can trigger graph validation and proposal generation.
- AI can manage graph repairs when policy allows.
- humans can review batches at the level of evidence and meaning, not only
  low-level graph mechanics.
- AI evidence decisions are auditable, hash-bound, policy-checked, and
  replay-safe.
- the DB can explain why a change was applied, blocked, or sent to review.

## Target Architecture

### Package Boundary

Target structure:

```text
services/artana_evidence_db/
  app.py
  config.py
  database.py
  routers/
  graph_api_schemas/
  core/
    validation/
    dictionary/
    graph/
    projection/
    proposals/
    packs/
  domain_packs/
    biomedical/
    sports_example/
  docs/
```

This structure can be reached incrementally. The exact folders can change, but
the ownership boundary should not.

### Runtime Flow

```text
service startup
  -> load settings
  -> register built-in packs
  -> resolve active pack from GRAPH_DOMAIN_PACK
  -> initialize service using active pack
  -> do not run domain seeding unless configured or requested
```

### Pack Registry

The DB service needs a small pack registry:

```text
register_graph_domain_pack(pack)
list_graph_domain_packs()
resolve_graph_domain_pack(name)
get_active_graph_domain_pack()
```

Required pack metadata:

- `name`
- `version`
- `display_name`
- `description`
- `engine_min_version`
- `engine_max_version`, optional
- `dictionary_loading_extension`
- `view_extension`
- `relation_suggestion_extension`
- `autopromotion_defaults`

The registry should fail fast when:

- `GRAPH_DOMAIN_PACK` names an unsupported pack.
- a pack version is incompatible with the engine version.
- two packs register the same name.

### Domain Pack Boundary

Domain packs may provide:

- dictionary definitions
- constraints
- default relation profiles
- pack-specific graph views
- deterministic source defaults
- seed concept templates

Domain packs may not:

- override core claim invariants
- bypass relation constraint validation
- mutate official dictionary state without governance
- include LLM prompts that are executed by the DB service
- import AI-service runtime code

### Artana Kernel Boundary

Artana Kernel belongs in the AI layer for V2.

`services/artana_evidence_api` should use Artana Kernel for:

- document extraction
- graph chat
- relation/entity disambiguation
- dictionary proposal drafting
- hypothesis exploration
- claim curation assistance
- literature refresh
- ranking and summarization

`services/artana_evidence_db` should not directly run Artana Kernel agents.

The DB service may store:

- `agent_run_id`
- `model_id`
- `model_version`
- `prompt_id`
- `prompt_version`
- `tool_trace_ref`
- evidence references
- confidence/rationale fields
- proposal provenance

The DB service should validate that AI-authored writes contain enough metadata
for auditability, but it should not call the model.

## Ideal V2 API Surface

This section is a capability map, not a recommendation to expose a confusing
top-level endpoint for every user scenario. The public API should stay organized
around a small number of stable families:

```text
spaces
dictionary
graph resources
validation
proposals
workflows
explanations
maintenance
```

Design rules:

- add a new endpoint family only for a durable core resource.
- add new human/AI product modes as typed `workflows`, not as new top-level
  route groups.
- keep low-level APIs available for advanced clients, but make common product
  tasks possible through one workflow endpoint.
- prefer `kind`, `status`, `action`, and `generated_resources` fields over
  many nearly identical endpoint names.
- every workflow must call the same lower-level validators and proposal
  services as direct API users.

### Service And Pack Introspection

```text
GET /health
GET /v1/info
GET /v1/capabilities
GET /v1/domain-packs
GET /v1/domain-packs/{pack_name}
GET /v1/domain-packs/active
GET /v1/domain-packs/{pack_name}/spaces/{space_id}/seed-status
POST /v1/domain-packs/{pack_name}/spaces/{space_id}/seed
POST /v1/domain-packs/{pack_name}/spaces/{space_id}/repair
```

Purpose:

- tell external projects what the service supports
- expose active pack identity and version
- make deployment configuration inspectable

### Graph Spaces

```text
GET /v1/admin/spaces
POST /v1/admin/spaces
GET /v1/admin/spaces/{space_id}
PATCH /v1/admin/spaces/{space_id}
POST /v1/admin/spaces/{space_id}/sync
```

Memberships:

```text
GET /v1/admin/spaces/{space_id}/memberships
PUT /v1/admin/spaces/{space_id}/memberships/{user_id}
DELETE /v1/admin/spaces/{space_id}/memberships/{user_id}
```

V2 addition:

- `seed-status` records pack name, pack version, seeded concept templates,
  seeded dictionary snapshot, and last seed operation.

### Dictionary Governance

Official dictionary APIs:

```text
GET /v1/dictionary/domain-contexts
GET /v1/dictionary/entity-types
POST /v1/dictionary/entity-types
GET /v1/dictionary/entity-types/{entity_type}
PATCH /v1/dictionary/entity-types/{entity_type}
POST /v1/dictionary/entity-types/{entity_type}/revoke
POST /v1/dictionary/entity-types/{entity_type}/merge

GET /v1/dictionary/relation-types
POST /v1/dictionary/relation-types
GET /v1/dictionary/relation-types/{relation_type}
PATCH /v1/dictionary/relation-types/{relation_type}
POST /v1/dictionary/relation-types/{relation_type}/revoke
POST /v1/dictionary/relation-types/{relation_type}/merge

GET /v1/dictionary/relation-constraints
POST /v1/dictionary/relation-constraints

GET /v1/dictionary/variables
POST /v1/dictionary/variables
GET /v1/dictionary/value-sets
POST /v1/dictionary/value-sets
GET /v1/dictionary/changelog
```

V2 requirement:

- official dictionary mutation requires graph-admin or dictionary-governance
  role.
- every mutation writes changelog and provenance.
- every mutation is idempotent through a stable `source_ref` or
  `Idempotency-Key`.

### Dictionary Proposal APIs

New governed proposal APIs:

```text
GET /v1/dictionary/proposals
POST /v1/dictionary/proposals/domain-contexts
POST /v1/dictionary/proposals/entity-types
POST /v1/dictionary/proposals/relation-types
POST /v1/dictionary/proposals/relation-constraints
POST /v1/dictionary/proposals/relation-synonyms
POST /v1/dictionary/proposals/variables
POST /v1/dictionary/proposals/value-sets
POST /v1/dictionary/proposals/value-sets/{value_set_id}/items
GET /v1/dictionary/proposals/{proposal_id}
POST /v1/dictionary/proposals/{proposal_id}/approve
POST /v1/dictionary/proposals/{proposal_id}/reject
POST /v1/dictionary/proposals/{proposal_id}/merge
POST /v1/dictionary/proposals/{proposal_id}/request-changes
```

Proposal status:

```text
SUBMITTED
CHANGES_REQUESTED
APPROVED
REJECTED
MERGED
```

Proposal payload must include:

- proposed object
- rationale
- evidence references
- overlap analysis with existing dictionary entries
- author kind: human, ai_agent, system
- provenance envelope
- suggested migration effect

Example:

```json
{
  "proposal_type": "relation_type",
  "proposed_id": "SENSITIZES_TO",
  "display_name": "Sensitizes To",
  "description": "Source increases sensitivity to a target intervention.",
  "rationale": "Existing relation types lose the treatment-sensitivity meaning.",
  "evidence": [
    {
      "source_document_ref": "pubmed:12345",
      "sentence": "BRCA1 loss sensitized cells to cisplatin."
    }
  ],
  "suggested_constraints": [
    {
      "source_type": "GENE",
      "relation_type": "SENSITIZES_TO",
      "target_type": "DRUG"
    }
  ]
}
```

### Validation APIs

Side-effect-free validators:

```text
POST /v1/spaces/{space_id}/validate/entity
POST /v1/spaces/{space_id}/validate/observation
POST /v1/spaces/{space_id}/validate/triple
POST /v1/spaces/{space_id}/validate/claim
POST /v1/dictionary/validate/entity-type
POST /v1/dictionary/validate/relation-type
POST /v1/dictionary/validate/relation-constraint
```

Validation response:

```json
{
  "valid": false,
  "code": "unknown_relation_type",
  "message": "Relation type SENSITIZES_TO is not approved.",
  "severity": "blocking",
  "claim_ids": [],
  "next_actions": [
    {
      "action": "create_dictionary_proposal",
      "proposal_type": "relation_type",
      "reason": "No approved relation type captures this meaning."
    }
  ]
}
```

Stable validation codes:

- `allowed`
- `unknown_entity_type`
- `inactive_entity_type`
- `unknown_relation_type`
- `invalid_relation_type`
- `relation_constraint_not_allowed`
- `relation_constraint_review_only`
- `missing_required_identifier`
- `duplicate_entity_candidate`
- `unknown_entity`
- `unknown_subject`
- `unknown_variable`
- `duplicate_claim`
- `conflicting_claim`
- `invalid_value_for_variable`
- `missing_provenance`
- `unknown_provenance`
- `cross_space_provenance`
- `insufficient_evidence`
- `permission_denied`

### Entities

```text
GET /v1/spaces/{space_id}/entities
POST /v1/spaces/{space_id}/entities
POST /v1/spaces/{space_id}/entities/resolve
POST /v1/spaces/{space_id}/entities/batch
GET /v1/spaces/{space_id}/entities/{entity_id}
PATCH /v1/spaces/{space_id}/entities/{entity_id}
DELETE /v1/spaces/{space_id}/entities/{entity_id}
POST /v1/spaces/{space_id}/entities/{entity_id}/merge
```

Identifiers and aliases:

```text
GET /v1/spaces/{space_id}/entities/{entity_id}/identifiers
POST /v1/spaces/{space_id}/entities/{entity_id}/identifiers
GET /v1/spaces/{space_id}/entities/{entity_id}/aliases
POST /v1/spaces/{space_id}/entities/{entity_id}/aliases
```

V2 requirements:

- entity creation uses active dictionary entity resolution policies.
- entity APIs return resolution explanation.
- PHI-sensitive identifiers remain isolated and encrypted when enabled.
- merge operations preserve provenance and redirect graph references.

### Observations

```text
GET /v1/spaces/{space_id}/observations
POST /v1/spaces/{space_id}/observations
GET /v1/spaces/{space_id}/observations/{observation_id}
PATCH /v1/spaces/{space_id}/observations/{observation_id}
DELETE /v1/spaces/{space_id}/observations/{observation_id}
```

V2 requirements:

- variable must exist.
- exactly one typed value column is populated.
- value type must match variable data type.
- dictionary constraints must be enforced.
- provenance is required for non-manual observations.

### Claims And Claim Evidence

Claims are candidate statements, not official graph truth.

```text
GET /v1/spaces/{space_id}/claims
POST /v1/spaces/{space_id}/claims
GET /v1/spaces/{space_id}/claims/{claim_id}
PATCH /v1/spaces/{space_id}/claims/{claim_id}
POST /v1/spaces/{space_id}/claims/{claim_id}/triage

GET /v1/spaces/{space_id}/claims/{claim_id}/participants
POST /v1/spaces/{space_id}/claims/{claim_id}/participants

GET /v1/spaces/{space_id}/claims/{claim_id}/evidence
POST /v1/spaces/{space_id}/claims/{claim_id}/evidence
```

V2 claim status:

```text
OPEN
PENDING_DICTIONARY_REVIEW
PENDING_EVIDENCE_REVIEW
APPROVED_FOR_PROJECTION
PROJECTED
REJECTED
QUARANTINED
SUPERSEDED
```

AI-authored claim payload must include:

- `agent_run_id`
- `model_id`
- `model_version`
- `prompt_id`
- `prompt_version`
- `input_hash`
- evidence references
- assessment
- rationale
- source document reference

### Claim Promotion And Canonical Relations

```text
GET /v1/spaces/{space_id}/relations
POST /v1/spaces/{space_id}/relations
GET /v1/spaces/{space_id}/relations/{relation_id}
PATCH /v1/spaces/{space_id}/relations/{relation_id}
POST /v1/spaces/{space_id}/relations/{relation_id}/approve
POST /v1/spaces/{space_id}/relations/{relation_id}/reject
POST /v1/spaces/{space_id}/relations/{relation_id}/retract

POST /v1/spaces/{space_id}/claims/{claim_id}/promote
POST /v1/spaces/{space_id}/claims/promote-batch
```

Core evidence invariant:

```text
If dictionary.requires_evidence(source_type, relation_type, target_type) is true,
then a claim may be stored without evidence, but it must remain non-persistable
and must not promote or materialize into a canonical relation until at least one
accepted evidence row is attached.
```

`FactAssessment` is not enough by itself. It records confidence, grounding,
mapping status, speculation, and rationale. Evidence is the source-backed
support attached to the claim or relation, such as an evidence sentence, source
document reference, provenance ID, figure/table reference, or external document
link.

### Evidence Records And Source Links

V2 does not introduce evidence from zero. The current graph service already has
two evidence surfaces:

```text
claim_evidence
  = evidence attached to a relation claim before or during review

relation_evidence
  = derived evidence attached to a canonical relation after projection
```

Current `claim_evidence` rows already support:

- `claim_id`
- `source_document_id`
- `source_document_ref`
- `agent_run_id`
- `sentence`
- `sentence_source`
- `sentence_confidence`
- `sentence_rationale`
- `figure_reference`
- `table_reference`
- `confidence`
- `metadata_payload`
- `created_at`

Current `relation_evidence` rows already support:

- `relation_id`
- `confidence`
- `evidence_summary`
- `evidence_sentence`
- `evidence_sentence_source`
- `evidence_sentence_confidence`
- `evidence_sentence_rationale`
- `evidence_tier`
- `provenance_id`
- `source_document_id`
- `source_document_ref`
- `agent_run_id`
- `created_at`

So the current code can already say:

```text
This claim or relation came from this source document or external reference.
This sentence, figure, table, or provenance record supports it.
This agent run or curator supplied it.
```

The V2 improvement is to make this evidence shape more explicit, governed, and
portable across domains. Some source metadata can currently live in
`metadata_payload`, but V2 should promote the important parts into a clearer
contract.

Recommended V2 evidence fields:

- `evidence_id`
- `source_kind`, such as `paper`, `web_page`, `pdf`, `database_record`,
  `curator_note`, `agent_output`
- `source_document_id`
- `source_document_ref`
- `source_url`
- `source_title`
- `source_authors`
- `source_publication_date`
- `source_version`
- `evidence_sentence`
- `evidence_excerpt`
- `evidence_locator`, such as page, paragraph, section, figure, or table
- `figure_reference`
- `table_reference`
- `confidence`
- `evidence_tier`
- `provenance_id`
- `agent_run_id`
- `review_status`
- `reviewed_by`
- `reviewed_at`
- `metadata`

The relation is the graph answer. The evidence row is the proof trail. A single
canonical relation can be supported by many evidence rows from papers, web
pages, PDFs, database records, AI extraction runs, or curator notes.

Promotion requirements:

- source and target entities exist in the same space.
- relation type is approved.
- active relation constraint allows the triple.
- evidence requirement is satisfied.
- duplicate canonical relation handling is deterministic.
- projection lineage is recorded in `relation_projection_sources`.
- curation status and reviewer metadata are preserved.

### Product Mode Orchestration APIs

The DB should expose product-mode APIs that combine validation, proposal
generation, policy, and audit into one reusable workflow. These APIs should be
optional convenience workflows over the lower-level primitives, not hidden
shortcuts around them.

Review finding:

```text
Avoid one endpoint family per human scenario.
```

The first draft listed separate endpoint families for evidence decisions,
review packets, AI evidence decisions, conflict resolution, and explanations.
That is too much surface area for a reusable DB product. External projects
should learn a few stable patterns:

- read/write graph resources
- validate candidate writes
- propose changes
- run a workflow
- explain a decision

Product modes should therefore use a small workflow API with typed `kind`,
`status`, and `action` fields. Internally, each workflow may create concept
proposals, dictionary proposals, graph-change proposals, AI decisions, claims,
evidence rows, or conflict records. The client should not need a different
endpoint family for every mode.

Operating mode configuration can stay small:

```text
GET /v1/spaces/{space_id}/operating-mode
PATCH /v1/spaces/{space_id}/operating-mode
GET /v1/spaces/{space_id}/operating-mode/capabilities
```

Unified product workflow API:

```text
POST /v1/spaces/{space_id}/workflows
GET /v1/spaces/{space_id}/workflows
GET /v1/spaces/{space_id}/workflows/{workflow_id}
POST /v1/spaces/{space_id}/workflows/{workflow_id}/actions
```

Recommended workflow kinds:

- `evidence_approval`
- `batch_review`
- `ai_evidence_decision`
- `conflict_resolution`
- `continuous_learning_review`
- `bootstrap_review`

Recommended workflow actions:

- `apply_plan`
- `approve`
- `reject`
- `request_changes`
- `split`
- `defer_to_human`
- `mark_resolved`

Example: human approves evidence, AI manages graph:

```json
{
  "kind": "evidence_approval",
  "mode": "human_evidence_ai_graph",
  "input": {
    "decision": "APPROVE_EVIDENCE",
    "source_label": "MED13",
    "relation_type": "ASSOCIATED_WITH",
    "target_label": "developmental delay",
    "evidence": {
      "source_document_ref": "pmid:123456",
      "evidence_sentence": "MED13 variants are associated with developmental delay.",
      "confidence": 0.91
    },
    "reviewed_by": "user:curator-123"
  },
  "source_ref": "curation-ui:evidence-review:abc123"
}
```

Example response:

```json
{
  "status": "GRAPH_REPAIR_REQUIRED",
  "kind": "evidence_approval",
  "operating_mode": "human_evidence_ai_graph",
  "workflow_id": "uuid",
  "validation": {
    "valid": false,
    "code": "unknown_target_concept"
  },
  "generated_resources": {
    "concept_proposal_ids": ["uuid"],
    "dictionary_proposal_ids": [],
    "graph_change_proposal_ids": ["uuid"],
    "claim_ids": [],
    "evidence_ids": []
  },
  "plan": {
    "next_action": "apply_plan",
    "requires_human": false,
    "policy_outcome": "ai_allowed_when_low_risk"
  },
  "next_action": "review_or_apply_graph_repair_plan"
}
```

Example action:

```json
{
  "action": "apply_plan",
  "actor": "ai:artana-kernel:graph-governor-v1",
  "decision_envelope": {
    "confidence": 0.94,
    "risk_tier": "low",
    "input_hash": "sha256:...",
    "evidence_refs": ["pmid:123456"],
    "rationale": "The target concept has an exact ontology match."
  }
}
```

The same `workflows` surface can represent batch review. A batch review
workflow groups:

- concept proposals
- dictionary proposals
- graph-change proposals
- evidence decisions
- claim promotion decisions
- connector proposals
- conflicts needing resolution

Keep explanation APIs narrow:

```text
GET /v1/spaces/{space_id}/explain/{resource_type}/{resource_id}
POST /v1/spaces/{space_id}/validate/explain
```

V2 rules:

- workflow APIs must call the same validators and proposal services as
  the lower-level APIs.
- a product-mode workflow must not silently mutate official graph state unless
  policy permits the exact decision.
- every generated repair plan must be replay-safe through `source_ref` or
  `Idempotency-Key`.
- every automatic step must write a decision, policy outcome, proposal hash,
  and evidence reference.
- each new workflow kind should be added as a typed payload under
  `/workflows`, not as a new top-level endpoint family, unless it becomes a
  core graph resource.

### Graph Reads

```text
GET /v1/spaces/{space_id}/graph/export
POST /v1/spaces/{space_id}/graph/subgraph
GET /v1/spaces/{space_id}/graph/neighborhood/{entity_id}
POST /v1/spaces/{space_id}/graph/document
GET /v1/spaces/{space_id}/graph/views/{view_type}/{resource_id}

POST /v1/search
GET /v1/search/suggest
GET /v1/search/stats

GET /v1/spaces/{space_id}/reasoning-paths
GET /v1/spaces/{space_id}/reasoning-paths/{path_id}
```

V2 rule:

- deterministic graph reads stay in DB.
- LLM-generated narrative answers live in `artana_evidence_api`.

### Suggestions And Embeddings

The boundary here must be explicit.

DB-owned:

- embedding storage
- embedding readiness
- nearest-neighbor lookup over stored vectors
- deterministic graph-overlap scoring
- dictionary-constrained relation suggestion candidates

AI-owned:

- model calls that produce embeddings
- LLM reranking
- hypothesis generation
- natural-language explanation
- chat answer synthesis

Possible V2 APIs:

```text
GET /v1/spaces/{space_id}/entities/embeddings/status
POST /v1/spaces/{space_id}/entities/embeddings
POST /v1/spaces/{space_id}/relations/suggestions
```

`POST /entities/embeddings` should accept vectors produced by an external AI
service. The DB service should not need an OpenAI key.

### Maintenance

```text
GET /v1/admin/operations/runs
GET /v1/admin/operations/runs/{run_id}
GET /v1/admin/projections/readiness
POST /v1/admin/projections/repair
POST /v1/admin/reasoning-paths/rebuild
POST /v1/admin/read-models/rebuild
POST /v1/domain-packs/{pack_name}/spaces/{space_id}/repair
```

V2 requirements:

- every operation records an operation run.
- operations are idempotent where possible.
- operations support dry-run mode.
- operation output includes counts, warnings, and repaired IDs.

## Implementation Plan

### Phase 0: Boundary Audit

Deliverables:

- inventory all imports from `services/artana_evidence_api` to
  `services/artana_evidence_db` and reverse imports.
- inventory all LLM prompt/model references inside `artana_evidence_db`.
- inventory all direct biomedical assumptions inside DB service files.
- list current endpoints that mutate dictionary state.
- list current AI-side graph client behavior that auto-creates dictionary
  state.

Exit criteria:

- a documented boundary leak list exists.
- each leak is tagged: move to DB, move to AI, keep but rename, or delete.

### Phase 1: Real Pack Registry

Deliverables:

- implement a service-local pack registry.
- add active-pack resolution from `GRAPH_DOMAIN_PACK`.
- add pack metadata and pack version.
- update `app.py`, `composition.py`, `dependencies.py`, governance builders,
  and seeders to consume active pack extensions.
- add `GET /v1/domain-packs` and `GET /v1/domain-packs/active`.

Exit criteria:

- `GRAPH_DOMAIN_PACK=biomedical` works through registry.
- unsupported pack name fails startup with a clear error.
- no generic DB composition code imports the biomedical pack directly.

### Phase 2: Minimal Non-Biomedical Reference Pack

Deliverables:

- add a small `sports_example` pack or `general_example` pack.
- include at least:
  - 3 domain contexts
  - 5 entity types
  - 6 relation types
  - 8 relation constraints
  - 1 graph view mapping
  - entity resolution policies
- run the existing core graph flows with this pack.

Exit criteria:

- entities can be created under the non-biomedical pack.
- relation constraints work under the non-biomedical pack.
- graph export, neighborhood, claims, and promotion work without biomedical
  vocabulary.

### Phase 3: Move AI Runtime Concerns Out Of DB

Deliverables:

- move LLM prompts from DB runtime into `services/artana_evidence_api`.
- move extraction fallback and entity-recognition heuristic orchestration into
  AI service.
- remove DB runtime need for Artana Kernel/OpenAI dependencies.
- replace DB prompt fields with opaque capability metadata where needed.
- ensure DB container can run without OpenAI or Artana runtime credentials.

Exit criteria:

- `services/artana_evidence_db/requirements.txt` does not need AI runtime
  packages.
- no DB service code calls Artana Kernel.
- graph DB tests pass with no `OPENAI_API_KEY`.
- AI service can still use Artana Kernel and call DB APIs.

Status:

- Complete in this slice. DB runtime packs now expose only opaque agent
  capability metadata; prompt dispatch, compact-record shaping, bootstrap
  defaults, and deterministic AI fallback config live in the AI-side runtime
  config.
- The biomedical prompt module was removed from
  `services/artana_evidence_db/runtime`, and AI prompt ownership now resolves
  through `src/infrastructure/llm/prompts` plus
  `src/infrastructure/llm/graph_domain_ai_config.py`.
- Boundary regression coverage asserts that `GraphDomainPack` no longer exposes
  prompt, payload, fallback, bootstrap, graph-connection prompt, or graph-search
  extension fields.

### Phase 4: Dictionary Proposal Ledger

Deliverables:

- add proposal persistence models and migrations.
- add dictionary proposal APIs.
- add approval, rejection, merge, request-changes operations.
- add proposal changelog and provenance.
- add governance role checks.
- update AI-side graph client to call proposal APIs instead of hidden
  auto-provisioning.

Exit criteria:

- unknown relation type can be proposed and reviewed.
- approved proposal creates official dictionary state.
- rejected proposal does not change official dictionary state.
- merged proposal points to the chosen canonical dictionary entry.

Status:

- Entry slice complete. The graph DB owns proposal persistence, review APIs,
  governance checks, and approval/rejection/merge/request-changes lifecycle for
  domain contexts, entity types, relation types, relation constraints, relation
  synonyms, variables, value sets, and value-set items.
- Proposal creation and lifecycle decisions write immutable entries to
  `dictionary_changelog` with `table_name=dictionary_proposals`, so proposal
  provenance and before/after review state are inspectable through
  `GET /v1/dictionary/changelog`.
- The AI-side graph client uses proposal APIs when validation discovers missing
  entity types, relation types, or relation constraints instead of silently
  creating official dictionary state.

### Phase 5: First-Class Validation APIs

Status:

- Entry slice complete. The graph DB exposes side-effect-free validation
  endpoints for entity, observation, triple, claim, and dictionary checks.
- Validation responses publish stable codes in the OpenAPI schema and include
  `claim_ids` when an existing claim blocks a candidate write.
- Claim validation and claim writes now share duplicate/conflict checks through
  the graph validation service, so `/validate/claim` can preflight the same
  blocking conditions returned by `POST /claims`.

Deliverables:

- implement validation services for entity, observation, triple, claim, and
  dictionary objects.
- route write paths through the same validators.
- publish stable validation codes in OpenAPI.
- add `dry_run` support to selected mutation endpoints or separate validation
  endpoints.

Exit criteria:

- validation-only and write paths agree.
- AI service can preflight candidate writes without persistence.
- invalid writes return actionable next actions.

### Phase 6: Claim Governance And Promotion Hardening

Status:

- Complete. AI-authored claim writes now require `agent_run_id` plus an
  `ai_provenance` envelope with model, prompt, input hash, rationale, and
  evidence references.
- Complete. Claim writes and dictionary proposal writes support replay-safe
  idempotency through either request `source_ref` or the `Idempotency-Key`
  header. Proposal `Idempotency-Key` values are scoped to the proposing actor
  so two users cannot accidentally replay each other's proposal record.
- Complete. Claim duplicate/conflict checks return stable responses, and
  proposal retries reuse the original proposal only when the proposal identity
  matches.
- Complete. Claim resolution no longer creates or activates dictionary
  dependencies. A claim can promote only when an active exact relation
  constraint already exists with `ALLOWED` or `EXPECTED` governance.
- Complete. Projection materialization records `relation_projection_sources`
  lineage and remains idempotent when the same resolved claim is processed
  again.

Deliverables:

- require AI-authored provenance envelope for AI claim writes.
- add idempotency support for claim and proposal writes.
- strengthen duplicate and conflict checks.
- separate proposal acceptance from canonical relation projection.
- ensure projection lineage is always recorded.

Exit criteria:

- retries do not create duplicate claims.
- duplicate claims return stable conflict responses.
- claims blocked by dictionary review remain queryable but cannot promote.
- approved claims promote deterministically.

### Phase 7: Pack-Versioned Seeding

Status:

- Complete. Startup no longer opens a database session or seeds biomedical
  starter concepts for every existing graph space.
- Complete. Graph space create and sync routes only manage registry and
  membership state; they do not create biomedical concept sets.
- Complete. `graph_pack_seed_status` records pack name, pack version, seed and
  repair counts, last operation, timestamps, and pack metadata.
- Complete. Admin endpoints now seed, repair, and inspect seed status for one
  pack and one graph space explicitly.
- Complete. Biomedical pack seeding creates biomedical starter concepts, while
  the sports reference pack seeds only its dictionary and creates no biomedical
  concept sets.

Deliverables:

- add pack seed status model.
- add explicit seed and repair APIs.
- remove unconditional biomedical starter seeding from startup.
- seed new spaces through explicit lifecycle event or admin operation.

Exit criteria:

- startup does not mutate every existing space.
- seed operation records pack name and pack version.
- repeated seed operation is idempotent.
- non-biomedical pack seed does not create biomedical concepts.

### Phase 8: Client And Contract Cleanup

Status:

- Complete. OpenAPI and generated TypeScript contracts include validation,
  proposal, pack introspection, and pack seed/status schemas.
- Complete. `services/artana_evidence_api/graph_client.py` uses graph DB
  validation and dictionary proposal APIs for preflight repair paths instead of
  official dictionary mutation APIs.
- Complete. The artana-evidence-api boundary check now rejects production
  calls to official graph dictionary mutation endpoints; proposal endpoints
  remain the allowed path.
- Complete. A small HTTP-only external client example covers health, pack
  discovery, graph-space sync, pack seeding, entity validation/creation, claim
  validation/creation, and graph export.

Deliverables:

- regenerate OpenAPI.
- update generated TypeScript contract.
- update `services/artana_evidence_api/graph_client.py` to use proposal and
  validation APIs.
- remove AI-side hidden dictionary auto-provisioning.
- provide a small external-example client flow.

Exit criteria:

- external clients can run core DB flows over HTTP only.
- AI service uses DB APIs rather than DB internals.
- graph DB can be deployed without the platform service.

## AI Full Mode Governance (Phase 9)

V2 intentionally makes the DB safe first: AI can propose, and the DB decides
what is valid and official. Phase 9 adds an explicit AI Full Mode where trusted
AI agents can also make approval decisions. This does not mean hidden mutation.
It means the DB accepts AI decisions only through a governed, auditable decision
workflow.

Target operating modes:

```text
human_review
  AI proposes.
  Human curator/admin approves, rejects, or merges.

ai_assisted
  AI proposes and recommends a decision.
  Human curator/admin approves high-impact changes.

ai_full
  AI proposes, AI reviews, AI decides.
  DB validates policy, applies allowed changes, and records the full audit trail.
```

### Design Principle

AI may be allowed to decide, but the DB still owns official truth.

The DB must enforce:

- the AI actor is authenticated.
- the AI actor is authorized for the requested decision.
- the proposed change is valid against the active domain pack.
- the evidence/rationale/confidence envelope is complete.
- risk policy allows AI approval for this change.
- duplicate, synonym, and conflict checks have passed.
- every official mutation is reversible or at least auditable.

The DB should never accept an opaque "just do it" model response.

### AI Decision Envelope

All AI-made decisions should include a typed decision envelope:

```json
{
  "decision_by": "ai:artana-kernel:graph-governor-v1",
  "decision": "APPROVE",
  "confidence": 0.94,
  "risk_level": "LOW",
  "rationale": "Exact external ontology match to HPO:0001263.",
  "evidence_refs": ["pmid:123456", "hpo:HPO:0001263"],
  "model_id": "artana-kernel",
  "model_version": "graph-governor-v1",
  "prompt_id": "concept-resolution-review",
  "prompt_version": "2026-04",
  "input_hash": "sha256:...",
  "tool_trace_ref": "artana-run:...",
  "rollback_plan": "Remove synonym DD from concept HPO:0001263."
}
```

Required DB checks:

- `decision_by` must map to a known AI principal.
- `decision` must be one of `APPROVE`, `REJECT`, `MERGE`,
  `REQUEST_CHANGES`, `DEFER_TO_HUMAN`, or `APPLY_RESOLUTION_PLAN`.
- `confidence` must meet the policy threshold for the change type.
- `risk_level` must be allowed for the governance mode.
- `input_hash` must match the proposal snapshot being decided.
- `evidence_refs` must point to stored evidence, source documents, or trusted
  external references.
- `rollback_plan` is required for automatic official dictionary changes.

### Concept Proposal Model

V2 has dictionary proposals for types and relation rules. AI Full Mode needs
first-class proposals for actual concepts/entities, not only dictionary
categories.

Concept proposal request:

```http
POST /v1/concepts/proposals
```

Example payload:

```json
{
  "entity_type": "PHENOTYPE",
  "canonical_label": "developmental delay",
  "synonyms": ["DD", "delayed development"],
  "external_refs": [
    {
      "namespace": "HPO",
      "identifier": "HP:0001263"
    }
  ],
  "evidence": [
    {
      "source_ref": "pmid:123456",
      "quote": "patients showed developmental delay",
      "confidence": 0.91
    }
  ],
  "rationale": "The document uses a phenotype already represented in HPO.",
  "source_ref": "ai-run:abc123:concept:developmental-delay"
}
```

The DB response should include a resolution result:

```json
{
  "status": "REVIEW_REQUIRED",
  "candidate_decision": "MERGE_AS_SYNONYM",
  "existing_concept_id": "concept:hpo:HP:0001263",
  "duplicate_checks": [
    {
      "kind": "external_ref",
      "result": "EXACT_MATCH",
      "matched_id": "concept:hpo:HP:0001263"
    },
    {
      "kind": "synonym",
      "result": "AMBIGUOUS_MATCH",
      "value": "DD"
    }
  ],
  "warnings": [
    {
      "code": "ambiguous_synonym",
      "message": "DD is short and may refer to multiple concepts."
    }
  ]
}
```

Concept proposal statuses:

- `SUBMITTED`
- `DUPLICATE_CANDIDATE`
- `MERGE_RECOMMENDED`
- `CHANGES_REQUESTED`
- `APPROVED`
- `MERGED`
- `REJECTED`
- `AUTO_APPLIED`

### Concept Relation Proposal Model

A concept relation proposal is an actual candidate connection between two
concepts or entities.

Examples:

```text
MED13 ASSOCIATED_WITH developmental delay
Lionel Messi PLAYS_FOR Inter Miami
Apple Inc. FOUNDED_BY Steve Jobs
```

Request:

```http
POST /v1/claims/proposals
```

Example payload:

```json
{
  "source": {
    "label": "MED13",
    "entity_type": "GENE",
    "external_refs": [{"namespace": "HGNC", "identifier": "22474"}]
  },
  "relation_type": "ASSOCIATED_WITH",
  "target": {
    "label": "developmental delay",
    "entity_type": "PHENOTYPE",
    "external_refs": [{"namespace": "HPO", "identifier": "HP:0001263"}]
  },
  "evidence": [
    {
      "source_ref": "pmid:123456",
      "quote": "MED13 variants are associated with developmental delay",
      "confidence": 0.88
    }
  ],
  "source_ref": "ai-run:abc123:claim:med13-dd"
}
```

Validation order:

1. Resolve or propose source concept.
2. Resolve or propose target concept.
3. Validate relation type exists and is active.
4. Validate relation constraint is allowed for source/target types.
5. Check evidence requirements.
6. Check duplicate claims.
7. Check conflicting claims.
8. Return an apply plan or review-required result.

Possible outcomes:

- `CREATE_CLAIM`
- `DUPLICATE_CLAIM`
- `CONFLICTING_CLAIM`
- `UNKNOWN_SOURCE_CONCEPT`
- `UNKNOWN_TARGET_CONCEPT`
- `UNKNOWN_RELATION_TYPE`
- `RELATION_CONSTRAINT_NOT_ALLOWED`
- `INSUFFICIENT_EVIDENCE`
- `REVIEW_REQUIRED`

### Graph Change Proposal Bundles

AI Full Mode needs to support complete mini-graph proposals. A single AI run
may discover concepts, synonyms, external references, and relations that only
make sense together.

Request:

```http
POST /v1/graph-change-proposals
```

Example payload:

```json
{
  "concepts": [
    {
      "local_id": "c1",
      "entity_type": "GENE",
      "canonical_label": "MED13",
      "synonyms": ["Mediator complex subunit 13"],
      "external_refs": [{"namespace": "HGNC", "identifier": "22474"}]
    },
    {
      "local_id": "c2",
      "entity_type": "PHENOTYPE",
      "canonical_label": "developmental delay",
      "synonyms": ["DD"],
      "external_refs": [{"namespace": "HPO", "identifier": "HP:0001263"}]
    }
  ],
  "claims": [
    {
      "source": "c1",
      "relation_type": "ASSOCIATED_WITH",
      "target": "c2",
      "evidence_ref": "e1"
    }
  ],
  "evidence": [
    {
      "local_id": "e1",
      "source_ref": "pmid:123456",
      "quote": "MED13 variants are associated with developmental delay"
    }
  ],
  "source_ref": "ai-run:abc123:graph-change"
}
```

The DB should not apply the bundle directly. It should create a deterministic
resolution plan:

```json
{
  "status": "REVIEW_REQUIRED",
  "resolution_plan": {
    "concepts": [
      {
        "local_id": "c1",
        "decision": "MATCH_EXISTING",
        "existing_id": "concept:hgnc:22474"
      },
      {
        "local_id": "c2",
        "decision": "MERGE_SYNONYM",
        "existing_id": "concept:hpo:HP:0001263",
        "new_synonyms": ["DD"]
      }
    ],
    "claims": [
      {
        "decision": "CREATE_CLAIM",
        "source": "concept:hgnc:22474",
        "relation_type": "ASSOCIATED_WITH",
        "target": "concept:hpo:HP:0001263"
      }
    ]
  },
  "warnings": [
    {
      "code": "AMBIGUOUS_SYNONYM",
      "label": "DD",
      "message": "DD may mean developmental delay or drug dosage."
    }
  ]
}
```

In `human_review` mode, a person reviews this plan.

In `ai_full` mode, an authorized AI judge can submit:

```http
POST /v1/graph-change-proposals/{proposal_id}/ai-decisions
```

The DB applies the plan only if policy allows the AI decision.

### Synonym And Duplicate Resolution

Synonyms must be treated as possible aliases of existing concepts, not as
proof that a new concept should be created.

Resolution pipeline:

1. Normalize label and synonyms.
2. Check exact canonical-label match within the same entity type and domain.
3. Check exact synonym match.
4. Check external reference match.
5. Check normalized acronym/short-label collision.
6. Check fuzzy text similarity.
7. Check embedding similarity if vectors are available.
8. Ask an AI judge only for ambiguous cases and only if policy allows.
9. Return one of:
   - `MATCH_EXISTING`
   - `CREATE_NEW`
   - `MERGE_AS_SYNONYM`
   - `SYNONYM_COLLISION`
   - `POSSIBLE_DUPLICATE`
   - `REVIEW_REQUIRED`

Hard rules:

- An external reference may map to only one active concept unless the pack
  explicitly allows many-to-one mapping.
- A synonym may not point to two active concepts in the same domain context
  unless ambiguity is explicitly modeled.
- Short synonyms such as `DD`, `ID`, `RA`, or `MS` are high-risk by default.
- AI Full Mode may auto-merge exact external-reference matches.
- AI Full Mode should not auto-merge ambiguous short synonyms unless the risk
  policy explicitly allows it.

Synonym collision response:

```json
{
  "valid": false,
  "code": "synonym_collision",
  "message": "Synonym DD already belongs to concept HPO:0001263.",
  "existing_concept_id": "concept:hpo:HP:0001263",
  "next_actions": [
    {
      "action": "merge_with_existing_concept",
      "target": "/v1/concepts/proposals"
    },
    {
      "action": "request_human_review",
      "target": "/v1/concepts/review"
    }
  ]
}
```

### AI Full Mode Policy

AI Full Mode should be controlled by space and operation policy, not one global
boolean.

Example policy:

```json
{
  "governance_mode": "ai_full",
  "dictionary_changes": {
    "synonym_add": "ai_allowed",
    "concept_merge_exact_external_ref": "ai_allowed",
    "new_entity_type": "human_required",
    "new_relation_type": "human_required",
    "new_relation_constraint": "ai_allowed_when_low_risk"
  },
  "claim_changes": {
    "create_claim": "ai_allowed",
    "promote_claim": "ai_allowed_when_evidence_required_satisfied",
    "resolve_conflict": "human_required"
  },
  "risk_thresholds": {
    "LOW": 0.85,
    "MEDIUM": 0.92,
    "HIGH": 0.98
  }
}
```

Risk tiers:

- `LOW`: exact external ontology match, exact duplicate merge, synonym from
  trusted ontology, duplicate claim detection.
- `MEDIUM`: new concept without external reference, new relation between known
  concepts, non-critical relation constraint.
- `HIGH`: new entity type, new relation type, revocation, destructive merge,
  PHI-sensitive mapping, bulk graph update, conflicting evidence resolution.

Default recommendation:

- `human_review` should remain the default.
- `ai_assisted` should be enabled first.
- `ai_full` should require explicit per-space enablement and audit visibility.

### Connector Proposals

Connectors are different from graph concepts. A connector is code or
configuration that retrieves data from an external source. The DB should not
generate or execute connector code.

However, AI may propose connector metadata:

```http
POST /v1/source-connectors/proposals
```

Possible payload:

```json
{
  "name": "ClinicalTrials.gov",
  "source_type": "clinical_trials",
  "description": "Connector for trial metadata and intervention/outcome facts.",
  "required_credentials": [],
  "proposed_mappings": [
    {
      "external_field": "conditions",
      "target_entity_type": "DISEASE"
    },
    {
      "external_field": "interventions",
      "target_entity_type": "DRUG"
    }
  ],
  "risk_level": "MEDIUM",
  "rationale": "The source provides evidence for treatment and condition relations."
}
```

The DB may store connector proposals and mappings, but connector execution
should live in an application, ingestion, or AI layer outside the DB.

### Implementation Plan For AI Full Mode

#### Phase 9.1: Concept Proposal Ledger

Status: implemented.

Deliverables:

- add concept proposal persistence models.
- add concept synonym proposal fields.
- add concept external-reference proposal fields.
- add concept proposal create/list/get/reject/request-changes APIs.
- add exact duplicate checks by label, synonym, and external reference.
- add changelog and audit events.

Exit criteria:

- AI or external clients can propose a concept over HTTP.
- duplicate concept proposals return a deterministic resolution result.
- synonyms do not create duplicate concepts by default.
- no official concept state changes before approval.

#### Phase 9.2: Concept Approval And Merge

Status: implemented.

Deliverables:

- add approve concept proposal operation.
- add merge concept proposal into existing concept operation.
- add synonym collision handling.
- add external-reference uniqueness enforcement.
- record before/after snapshots for concept changes.

Exit criteria:

- approved new concept creates official concept records.
- merged proposal adds aliases/synonyms to the existing concept.
- ambiguous synonym collision blocks auto-approval.
- repeat approval is idempotent.

#### Phase 9.3: Graph Change Proposal Bundles

Status: implemented.

Deliverables:

- add graph-change proposal schema.
- support local IDs for proposed concepts and claims.
- add deterministic resolution-plan builder.
- validate all concepts before validating claims.
- validate relation constraints and evidence requirements.
- add bundle-level duplicate/conflict reporting.

Exit criteria:

- a mini graph can be proposed in one HTTP request.
- DB returns a deterministic apply plan.
- invalid bundles are rejected without partial mutation.
- accepted bundles can be reviewed as one unit.

#### Phase 9.4: AI Decision Envelope

Status: implemented.

Deliverables:

- add AI decision schemas.
- add AI principal registry or trusted actor mapping.
- add decision hash binding to proposal snapshots.
- add policy checks for confidence, risk, and action type.
- add audit logging for AI decisions.

Exit criteria:

- AI can submit a decision without direct DB mutation access.
- DB rejects decisions with missing evidence, stale hashes, or insufficient
  confidence.
- every AI decision is inspectable and replay-safe.

#### Phase 9.5: AI Full Mode Policy

Status: implemented.

Deliverables:

- add per-space governance mode.
- add per-operation approval policy.
- add default risk thresholds.
- add `human_required`, `ai_allowed`, and `ai_allowed_when_low_risk` outcomes.
- add read APIs so clients can explain why a decision was blocked.

Exit criteria:

- AI Full Mode can be enabled for one test space without changing global
  behavior.
- high-risk changes still require human review by default.
- low-risk exact matches can be auto-applied by AI policy.
- all policy decisions are audited.

#### Phase 9.6: Connector Proposal Metadata

Status: implemented.

Deliverables:

- add connector proposal schema for metadata and mappings.
- keep connector execution outside the DB.
- add approval workflow for connector metadata.
- add mapping validation against active domain pack entity/relation/variable
  definitions.

Exit criteria:

- AI can propose a connector definition without deploying connector code.
- DB can approve connector metadata and field mappings.
- connector runtime remains outside `artana_evidence_db`.

### AI Full Mode Tests

Unit tests:

- exact label duplicate returns `MATCH_EXISTING`.
- exact synonym duplicate returns `MERGE_AS_SYNONYM`.
- ambiguous synonym returns `SYNONYM_COLLISION`.
- exact external reference match blocks duplicate concept creation.
- AI decision without evidence is rejected.
- AI decision with stale input hash is rejected.
- AI decision below confidence threshold is rejected.

Integration tests:

- propose concept, approve, and query official concept.
- propose duplicate concept and merge as synonym.
- propose mini graph and receive deterministic resolution plan.
- AI Full Mode auto-applies low-risk exact external-reference merge.
- AI Full Mode blocks high-risk new relation type without human policy.
- repeated graph-change proposal with same source ref is idempotent.

Regression tests:

- human-review mode behavior remains unchanged.
- AI Full Mode cannot bypass relation constraints.
- AI Full Mode cannot promote evidence-required claims without accepted
  evidence.
- AI Full Mode cannot mutate official dictionary state without a decision
  envelope.
- connector proposal approval does not execute connector code.

Security tests:

- only trusted AI principals can submit AI decisions.
- AI decision cannot act across spaces unless explicitly authorized.
- PHI-sensitive mappings are never auto-approved unless policy allows.
- every AI decision writes audit and changelog entries.

### AI Full Mode Acceptance Criteria

AI Full Mode is complete when:

- concepts can be proposed, resolved, approved, rejected, and merged through
  public APIs.
- graph-change bundles can propose concepts, synonyms, evidence, and claims in
  one request.
- synonym and duplicate detection prevents accidental duplicate concepts.
- AI decision envelopes can approve low-risk changes when policy allows.
- high-risk changes remain human-gated by default.
- every AI-made official change is auditable, evidence-backed, and replay-safe.
- external projects can use the same AI Full Mode APIs without depending on
  `services/artana_evidence_api` internals.

Phase 9 implementation notes:

- `concept_proposals` stores concept, synonym, external-reference,
  duplicate-check, source-ref, and proposal-hash state.
- `/v1/spaces/{space_id}/concepts/proposals` supports create, list, get,
  approve, reject, request-changes, and merge workflows.
- duplicate resolution checks exact canonical labels, exact aliases, and exact
  external references before official concept records are created.
- graph-change proposals accept local concepts and claims and return a
  deterministic resolution plan without partial mutation.
- `ai_full_mode_decisions` records trusted AI decision envelopes, confidence,
  risk tier, evidence, policy outcome, input hash, and apply/reject status.
- per-space `settings.ai_full_mode` controls `human_review`, `ai_assisted`, and
  `ai_full` behavior, trusted principals, confidence thresholds, and high-risk
  auto-approval.
- connector proposals store metadata and mappings only; approval explicitly
  records that connector runtime execution remains outside the graph DB.

## Product Operating Modes (Phase 10)

Phase 10 turns the V2 primitives into complete product workflows for the human
scenarios listed above. The goal is not to add hidden shortcuts. The goal is to
compose validation, proposals, evidence decisions, AI policy, and audit into
clear reusable flows that other projects can use without depending on
`services/artana_evidence_api`.

### Phase 10.1: Operating Mode Contract

Status: implemented in Phase 10.

Deliverables:

- add a typed `operating_mode` contract for graph spaces.
- support at least:
  - `manual`
  - `ai_assist_human_batch`
  - `human_evidence_ai_graph`
  - `ai_full_graph`
  - `ai_full_evidence`
  - `continuous_learning`
- expose mode read/update/capability endpoints.
- map each mode to allowed policy outcomes, risk thresholds, and required
  decision envelopes.
- keep `manual` as the safe default for new spaces.

Exit criteria:

- external clients can inspect the active mode for a space.
- changing mode persists into `graph_spaces.settings.operating_mode`.
- invalid modes are rejected by strict API schemas.
- mode policy is used by unified workflow actions and AI decision envelopes.

### Phase 10.2: Human Approves Evidence, AI Manages Graph

Status: implemented for the DB-owned workflow API. Follow-up work can broaden
descriptor resolution beyond explicit entity IDs and graph-change bundles.

This is the next highest-priority product slice.

Deliverables:

- add a durable `graph_workflows` ledger for evidence approvals.
- add a service that takes an evidence-approved claim shape and runs:
  1. source concept resolution
  2. target concept resolution
  3. relation type validation
  4. relation constraint validation
  5. evidence requirement validation
  6. duplicate/conflict detection
  7. graph repair plan generation
  8. optional AI decision submission when policy allows
  9. claim creation/promotion after the graph is valid
- create graph-change proposals automatically when evidence references missing
  graph pieces through a repair bundle.
- create dictionary proposals only when validation returns a missing rule.
- bind every generated proposal to the evidence decision through `source_ref`
  and proposal hashes.
- expose this through `POST /v1/spaces/{space_id}/workflows` with
  `kind=evidence_approval`, not a separate evidence-decision endpoint family.

Exit criteria:

- a user can approve evidence without manually creating concepts or relation
  constraints.
- if the graph is already valid, the DB creates the claim and can promote it
  according to policy.
- if concepts or rules are missing, the DB creates a graph repair plan.
- if AI Full Graph Mode policy allows the repair, the DB can apply it through
  AI decision envelopes.
- if policy blocks the repair, the plan remains reviewable and no partial
  official mutation occurs.

### Phase 10.3: AI Suggests, Human Batch Approves

Status: initial workflow envelope implemented. Full mixed-resource batch
application remains a follow-up hardening slice.

Deliverables:

- add review packet persistence.
- allow a packet to group concept, dictionary, graph-change, connector,
  evidence, claim, and conflict-resolution proposals.
- add approve/reject/split operations for packets.
- provide packet summaries:
  - low-risk count
  - high-risk count
  - conflicts
  - missing evidence
  - duplicate candidates
  - expected official mutations
- make packet operations idempotent and replay-safe.
- expose this through `POST /v1/spaces/{space_id}/workflows` with
  `kind=batch_review`.

Exit criteria:

- a human can approve a batch without clicking every low-risk item.
- high-risk items can be split out for separate review.
- packet approval applies each item through its normal governed service.
- packet failure reports the exact item and leaves already-applied idempotent
  items in a consistent state.

### Phase 10.4: AI Full Evidence Mode

Status: initial workflow envelope and policy-gated decision capture
implemented. Autonomous evidence acceptance remains human-gated by default.

Deliverables:

- add AI evidence decision envelopes distinct from graph-change decisions.
- define evidence risk tiers:
  - exact structured source record
  - quoted source sentence
  - inferred evidence from text
  - conflicting evidence
  - PHI-sensitive evidence
- require AI evidence decisions to include model, prompt, input hash,
  evidence locator, source reference, confidence, and rationale.
- add policy settings for whether AI can:
  - accept evidence
  - reject evidence
  - attach evidence to a claim
  - promote an evidence-backed claim
  - resolve evidence conflicts
- add replay-safe evidence extraction and decision records.
- expose this through `POST /v1/spaces/{space_id}/workflows` with
  `kind=ai_evidence_decision`.

Exit criteria:

- AI can accept low-risk evidence when policy allows.
- AI cannot promote an evidence-required claim unless accepted evidence exists.
- AI evidence decisions are queryable and explainable.
- stale evidence decisions are rejected when source/input hash changes.
- high-risk or conflicting evidence remains human-gated by default.

### Phase 10.5: Conflict Resolution Workflow

Status: initial workflow envelope implemented with governed resolution options.
Applying conflict decisions to affected claims remains follow-up work.

Deliverables:

- add conflict-resolution proposal records.
- support decisions:
  - `KEEP_BOTH`
  - `MARK_CONTEXT_SPECIFIC`
  - `PREFER_SOURCE`
  - `REJECT_SOURCE`
  - `REQUEST_MORE_EVIDENCE`
  - `DEFER_TO_HUMAN`
- attach conflict decisions to affected claims, relations, and evidence rows.
- expose conflict resolution through `POST /v1/spaces/{space_id}/workflows`
  with `kind=conflict_resolution`, not a separate conflict-resolution endpoint
  family.
- add policy rules for which conflict types AI may resolve.

Exit criteria:

- opposite-polarity claims can be grouped into one conflict-resolution case.
- the DB can explain which evidence supported each side.
- AI can resolve only low-risk conflicts when policy allows.
- unresolved conflicts remain visible in graph reads and review packets.

### Phase 10.6: Audit, Tutor, And Explanation APIs

Status: implemented for workflows, validation explanations, graph-change
proposals, and claims.

Deliverables:

- add explanation read APIs for proposals, decisions, claims, evidence, and
  canonical relations.
- return:
  - source evidence
  - validation checks
  - policy outcome
  - model/prompt identity
  - proposal hash
  - reviewer or AI principal
  - reason for blocking or applying
  - rollback or supersession information where available
- expose validation explanations for tutor-style clients.

Exit criteria:

- a user can ask why a relation exists and receive a deterministic audit
  answer.
- a user can ask why a write was blocked and receive a suggested next action.
- AI-service tutor/chat experiences can rely on DB-owned explanation payloads.

### Phase 10.7: Real AI Workflow Integration

Status: API client integration implemented. Live Artana Kernel workflow
smoke tests remain gated follow-up work because the DB service itself must
remain independent of OpenAI and Artana Kernel credentials.

Deliverables:

- update `services/artana_evidence_api` Artana harnesses to intentionally load
  `graph_harness.ai_full_mode` for workflows whose operating mode allows it.
- add end-to-end smoke tests where an Artana run:
  - proposes a concept
  - proposes a graph-change bundle
  - submits an AI decision
  - observes DB policy apply or block the change
- add live-model integration tests gated by `OPENAI_API_KEY`.
- keep DB tests independent of OpenAI keys.

Exit criteria:

- AI workflows use public DB APIs, not DB internals.
- live AI tests prove the tool wiring works with Artana Kernel.
- skipped live tests clearly explain missing environment keys.
- deterministic unit/integration tests still pass without external model
  access.

### Phase 10 Acceptance Criteria

Phase 10 is complete when:

- every graph space has a declared operating mode or safely defaults to
  `manual`.
- a human can approve valid evidence and let the DB create the governed claim.
- evidence workflows can create graph-repair and dictionary proposals instead
  of bypassing validation.
- AI workflow actions are policy-gated, trusted-principal-gated, and
  workflow-hash-gated.
- conflict resolution is represented as a first-class governed workflow.
- workflow, validation, claim, and graph-change resources can be explained
  through DB-owned explanation APIs.
- `services/artana_evidence_api` can exercise the modes through public
  `artana_evidence_db` APIs and typed contracts.
- other projects can use these same modes without adopting the full Artana
  application service.

## Test Strategy

The V2 product is stable only if tests prove both correctness and boundaries.

### Unit Tests

Core pack registry:

- registers one pack.
- rejects duplicate pack names.
- resolves active pack from `GRAPH_DOMAIN_PACK`.
- fails on unsupported pack.
- checks engine and pack version compatibility.

Dictionary validation:

- unknown entity type returns `unknown_entity_type`.
- unknown relation type returns `unknown_relation_type`.
- forbidden relation constraint blocks write.
- review-only constraint allows proposal but blocks auto-promotion.
- approved constraint allows claim and promotion.

Entity resolution:

- strict policy requires anchors.
- lookup policy resolves by identifier.
- fuzzy policy proposes candidates but does not silently merge ambiguous nodes.
- PHI-sensitive identifiers are routed through encrypted identifier behavior
  when enabled.

Claim validation:

- subject and object must exist.
- subject and object must be in the same space.
- subject and object cannot be the same entity.
- AI-authored claims require provenance envelope.
- missing evidence blocks evidence-required constraints.
- `FactAssessment` alone does not satisfy an evidence-required constraint.
- duplicate support claims return `duplicate_claim` with blocking `claim_ids`.
- opposing claims return `conflicting_claim` with blocking `claim_ids`.

Proposal ledger:

- proposal starts as `SUBMITTED`.
- approve mutates official dictionary once.
- reject leaves official dictionary unchanged.
- merge records canonical target.
- duplicate proposals are idempotent.

Projection:

- approved claim promotes to canonical relation.
- blocked claim cannot promote.
- duplicate canonical edge increments or links evidence deterministically.
- projection source lineage is recorded.

### Integration Tests

HTTP pack tests:

- service starts with biomedical pack.
- service starts with non-biomedical reference pack.
- `/v1/domain-packs/active` reports expected pack.
- dictionary endpoints return pack-specific contexts and types.

Graph flow tests:

- create space.
- seed pack.
- create entities.
- validate triple.
- create claim.
- attach evidence.
- approve claim.
- promote claim.
- export graph.
- fetch neighborhood.

Proposal flow tests:

- AI-style unknown relation creates dictionary proposal.
- proposal approval creates official relation type and constraint.
- rejected proposal cannot be used for promotion.
- merge proposal maps future candidates to existing type.

Product operating mode tests:

- new spaces default to the safe manual or human-review mode.
- invalid operating-mode transitions are rejected.
- human evidence approval creates a claim immediately when all graph
  dependencies are valid.
- human evidence approval creates a graph repair plan when a concept is
  missing.
- human evidence approval creates dictionary proposals when a relation type or
  relation constraint is missing.
- AI Full Graph Mode can apply a low-risk graph repair plan through AI decision
  envelopes.
- AI Full Graph Mode cannot apply a graph repair plan across spaces.
- AI Full Evidence Mode accepts low-risk evidence only when policy allows.
- AI Full Evidence Mode rejects stale evidence decisions when the source/input
  hash changed.
- batch review packet approval applies mixed proposal types through their
  normal governed services.
- batch review packet failure is idempotent and leaves applied items
  inspectable.
- conflict-resolution workflow keeps opposing evidence visible until a
  governed decision is applied.
- explanation APIs can answer why a claim, evidence row, relation, proposal, or
  AI decision was applied or blocked.

Authz tests:

- viewer can read.
- viewer cannot write.
- researcher can create claims where allowed.
- curator can triage/approve claims where allowed.
- graph admin can manage dictionary.
- non-member gets `403`.

Schema tests:

- PostgreSQL schema with `GRAPH_DB_SCHEMA=graph_runtime`.
- migrations apply cleanly from empty DB.
- dedicated schema does not leak into public schema.
- RLS session context is applied.

AI boundary tests:

- DB service starts without `OPENAI_API_KEY`.
- DB service has no direct Artana Kernel execution path.
- AI service can call validation and proposal APIs over HTTP.
- AI service hidden auto-provisioning is disabled or removed.

### Regression Tests

Boundary regression:

- no import from `services/artana_evidence_db.runtime.biomedical_pack` in generic
  DB composition code.
- no LLM prompt files under `services/artana_evidence_db/runtime`.
- no direct model/OpenAI/Artana Kernel calls in DB service code.
- AI service does not call dictionary official mutation APIs except through
  explicit proposal/approval flows.

Biomedical regression:

- existing biomedical entity types still seed.
- existing biomedical relation types still seed.
- existing biomedical relation constraints still seed.
- existing graph claim and projection flows continue to work.

Pack regression:

- non-biomedical pack can create a domain-specific entity such as `TEAM`.
- non-biomedical pack rejects biomedical-only entity types unless they are in
  the active pack.
- biomedical pack rejects non-biomedical-only entity types unless configured.

Idempotency regression:

- repeated claim create with same idempotency key returns same claim.
- repeated proposal create with same source ref returns same proposal.
- repeated seed operation does not duplicate dictionary entries.

Error-code regression:

- known invalid requests keep stable validation codes.
- OpenAPI examples match actual error payloads.

### Contract Tests

OpenAPI:

- export OpenAPI and check it is current.
- generated TypeScript client matches OpenAPI.
- validation error schemas are included.
- proposal schemas are included.
- pack introspection schemas are included.

Consumer contract:

- `services/artana_evidence_api` can use generated graph client only.
- no AI service code imports DB persistence models.
- external sample client can create a graph using HTTP only.

### Security Tests

Tenant isolation:

- one space cannot read another space's entities.
- one space cannot promote another space's claims.
- graph admin bypass is explicit and audited.

PHI:

- PHI-sensitive identifiers are encrypted when feature flag is enabled.
- blind indexes are used for lookup.
- non-PHI callers cannot retrieve protected identifiers.

Audit:

- dictionary official mutation is audited.
- proposal approval/rejection is audited.
- claim promotion is audited.
- graph admin operations are audited.

### Performance And Load Tests

Baseline scenarios:

- list entities with pagination.
- create batch entities.
- validate batch triples.
- export graph document.
- rebuild read models.
- relation suggestions over vector-ready entities.

Targets should be defined before implementation based on expected deployment
size. The initial goal is stable behavior and bounded queries, not maximum
throughput.

### Migration Tests

Required migration checks:

- empty database to latest head.
- existing biomedical database to V2 schema.
- proposal tables added without touching canonical graph rows.
- pack seed status backfill handles existing graph spaces.
- rollback strategy documented for each migration that changes official
  dictionary behavior.

## Acceptance Criteria

V2 is complete when:

- `artana_evidence_db` can run without `artana_evidence_api`.
- `artana_evidence_db` can run without OpenAI credentials.
- active domain pack is selected through a registry.
- at least two packs work through the same public APIs.
- official dictionary changes require explicit governance.
- AI can propose missing vocabulary without silently creating official rules.
- validation APIs explain why a candidate is accepted, blocked, or needs review.
- claim promotion is deterministic and auditable.
- OpenAPI is complete and generated clients can use the service over HTTP only.
- unit, integration, regression, contract, migration, and security tests pass.

## Non-Goals For V2

- dynamic third-party pack hot reload.
- fully remote pack marketplace.
- running LLM agents inside the DB service.
- replacing `services/artana_evidence_api`.
- removing biomedical support.
- optimizing all graph reads for very large graphs before the boundary is
  correct.

## Open Questions

- Should pack registration remain static at process startup, or should V2 allow
  admin-installed packs from a signed local bundle?
- Should relation suggestions remain in DB if they are purely deterministic, or
  move entirely to the AI service?
- Should claim writes with unknown relation types be stored as
  `PENDING_DICTIONARY_REVIEW`, or rejected until a dictionary proposal exists?
- What governance role should approve dictionary proposals: graph admin,
  dictionary curator, or space owner?
- Should dictionary proposals be global across all spaces or scoped to one
  graph space first?
- How much pack version drift is allowed between existing spaces in one
  deployment?

## Recommended First Implementation Slice

The first useful slice should be small and prove the boundary:

1. Add active pack registry and `/v1/domain-packs/active`.
2. Move startup code to resolve the active pack instead of importing biomedical
   config directly.
3. Add a tiny non-biomedical example pack.
4. Add tests that create one entity and one relation claim under both packs.
5. Add a boundary regression test that DB service imports no AI runtime.
6. Add dictionary proposal models and one relation-type proposal endpoint.
7. Update AI graph client to stop hidden relation-type auto-provisioning for
   that path and create a proposal instead.

This gives the project a real vertical proof:

```text
AI discovers missing relation
  -> DB stores proposal
  -> curator approves
  -> dictionary updates
  -> claim validates
  -> claim promotes
  -> graph exports
```

After that slice works, the remaining phases become incremental hardening
instead of architecture guesswork.

## Phase 11: Deterministic AI Confidence For Auto Mode

Status: implemented as the confidence-governance hardening layer for Phase 9
AI Full Mode and Phase 10 unified workflows.

The graph DB no longer treats an AI-authored numeric confidence as authority.
AI clients submit a qualitative `confidence_assessment`; the DB computes the
policy confidence used for auto-approval.

DB-owned scoring:

```text
computed_confidence = min(
  fact_assessment_weight,
  validation_cap,
  evidence_cap,
  duplicate_conflict_cap,
  source_reliability_cap,
  risk_cap
)
```

The score is a deterministic governance weight, not a true probability.

Hard blockers:

- invalid graph validation.
- required evidence missing.
- conflicting claim.
- stale workflow/proposal hash.
- cross-space resource.
- untrusted AI principal.

Human-review defaults:

- medium or high risk.
- review-required validation.
- possible duplicate.
- computed confidence below the space policy threshold.

Public API changes:

- `GraphWorkflowActionRequest` uses `confidence_assessment`; raw `confidence`
  is rejected.
- `AIDecisionSubmitRequest` uses `confidence_assessment`; raw `confidence` is
  rejected.
- graph-change claims use qualitative `assessment`; claim confidence is derived
  by the DB.
- AI decision responses expose `computed_confidence`,
  `confidence_assessment_payload`, and `confidence_model_version`.

Tests added or updated:

- scorer unit tests for strong evidence, ambiguous mapping, generated-only
  evidence, missing evidence, and conflicting claims.
- request-schema regression tests that reject raw AI confidence.
- graph-change claim tests proving confidence is derived from qualitative
  assessment.
- Phase 9/10 integration tests updated to submit qualitative assessments.
- contract artifacts regenerated so consumers see the new API shape.

## Phase 12: Workflow Governance Hardening

Status: implemented as the completion layer for Phase 10 workflows and Phase
11 deterministic confidence.

Phase 12 closes the review findings around AI authority, auditability,
batch application, composed evidence plans, service ownership of qualitative
assessment contracts, and workflow pagination counts.

Completed changes:

- AI authority is bound to authenticated identity. The request body still
  declares `ai_principal` for audit, but workflow AI actions and `/ai-decisions`
  require the authenticated JWT or test header principal to match that value.
- Workflow rejection attempts are recorded in `graph_workflow_events` before
  returning an error. Stale hashes, missing or mismatched AI principals,
  confidence blockers, policy blocks, human-review outcomes, and cross-space
  attempts stay inspectable.
- `batch_review` now applies mixed resource packets through the governed
  services for concept proposals, dictionary proposals, graph-change proposals,
  connector proposals, claims, and nested workflows.
- Batch review stores `applied_resource_refs`, `failed_resource_refs`, and
  `batch_results`. Partial failures move the workflow to
  `CHANGES_REQUESTED`; replaying the same batch is idempotent for already
  applied resources.
- Evidence approval planning composes claim validation, dictionary proposals,
  graph-change proposals, and pending claim state in one workflow. Official
  claim creation waits until required dictionary or graph repair resources are
  resolved.
- The graph DB owns its public `FactAssessment` contract and deterministic
  `assessment_confidence` helper locally, so `artana_evidence_db` no longer
  imports shared AI-agent contracts.
- Workflow list totals use SQL `count(*)`, preserving kind/status filters and
  avoiding the previous 10,000-row cap.

AI principal contract:

```json
{
  "graph_ai_principal": "agent:artana-kernel:graph-governor-v1"
}
```

Test-only auth can use:

```text
X-TEST-GRAPH-AI-PRINCIPAL: agent:artana-kernel:graph-governor-v1
```

Batch item contract:

```json
{
  "generated_resources": [
    {
      "resource_type": "concept_proposal",
      "resource_id": "...",
      "action": "approve",
      "input_hash": "...",
      "decision_payload": {},
      "reason": "..."
    }
  ]
}
```

Supported batch resources:

- `concept_proposal`: `approve`, `merge`, `reject`, `request_changes`.
- `dictionary_proposal`: `approve`, `reject`, `request_changes`.
- `graph_change_proposal`: `apply`, `reject`, `request_changes`.
- `connector_proposal`: `approve`, `reject`, `request_changes`.
- `claim`: `resolve`, `reject`, `needs_mapping`.
- `workflow`: `approve`, `reject`, `request_changes`, `defer_to_human`.

Regression coverage:

- authenticated AI principal parsing from JWT and test headers.
- forged AI workflow action rejection with a persisted workflow event.
- trusted matching AI workflow action in auto mode.
- mismatched `/ai-decisions` rejection persisted as an AI decision.
- composed evidence approval creates graph repair plus dictionary proposals
  without creating the claim early.
- mixed batch review applies valid resources, reports failed resources, and is
  replay-safe.
- workflow totals above 10,000 are counted correctly independent of page size.

## Phase 13: API Encapsulation And Shared Graph Preflight

Status: implemented as the API-side closure layer on top of Phase 12 DB
governance.

Phase 13 keeps the public DB workflow/proposal APIs stable, but refactors
`services/artana_evidence_api` so graph transport, AI resolution preflight,
authority binding, and governed submission are explicit internal
responsibilities instead of being mixed inside one client class.

Completed changes:

- `GraphTransportBundle` is now the normal typed graph surface for
  `artana_evidence_api`. It exposes query, validation, dictionary, and
  workflow transports without hiding proposal creation, relation rewrites, or
  AI preflight side effects inside transport methods.
- `GraphCallContext` now carries `user_id`, `role`, `graph_admin`,
  `graph_ai_principal`, `graph_service_capabilities`, and `request_id`.
  Graph-service JWTs are minted per call context instead of through one cached
  admin identity.
- Normal human/read flows do not silently attach AI authority. Only explicit
  AI-decision submission paths mint a token with `graph_ai_principal`.
- `GraphAIPreflightService` centralizes DB-first graph resolution:
  1. exact entity/display-label/alias resolution
  2. active relation synonym resolution
  3. active relation-type listing, synonym listing, dictionary search, and
     allowed-suggestion lookup for the current source/target pair
  4. Artana Kernel fallback only when deterministic graph checks are still
     ambiguous
- Relation resolution caches are scoped by graph space plus normalized label,
  so one space's synonym/mapping decision does not leak into another space.
- `GraphWorkflowSubmissionService` now owns governed submission assembly for
  concept proposals, graph-change proposals, AI decisions, workflows, and
  preflighted entity/claim/relation writes.
- Higher-level graph-writing callers in `artana_evidence_api` now route through
  the shared preflight/submission layer, including document extraction,
  proposal actions, research-init grounding, and AI Full Mode tools.
- Graph-facing DTOs in `artana_evidence_api` now use the DB-owned public
  `FactAssessment` contract shape rather than importing shared internal
  AI-agent contracts.

Internal API-side boundary:

```text
GraphCallContext
  -> GraphTransportBundle           # typed reads, validation, dictionary, workflow
  -> GraphRawMutationTransport      # internal-only direct mutation transport
  -> GraphAIPreflightService        # DB-first entity/relation resolution
  -> GraphWorkflowSubmissionService # governed write/proposal submission
```

Acceptance coverage:

- default graph-service tokens are not silently admin or AI-authority tokens.
- AI-authority submission paths attach `graph_ai_principal`; normal concept and
  graph-change proposal flows do not.
- transport-layer writes post raw payloads without hidden validation/proposal
  mutation.
- preflight resolves active DB relation synonyms before calling Artana Kernel.
- deterministic preflight paths skip Artana Kernel when a current graph match
  already exists.
- document extraction, proposal actions, research-init grounding, and AI Full
  Mode tool paths continue to produce governed graph outcomes through the
  shared boundary.

## Phase 14: Endpoint Architecture Closure

Status: implemented with strict boundary hardening and internal cleanup.

Phase 14 closes the remaining endpoint-architecture gaps between
`services/artana_evidence_api` and `services/artana_evidence_db` without
changing the public graph DB endpoint family.

Completed changes:

- The old all-purpose gateway surface was replaced by a typed transport split:
  - `GraphQueryTransport`
  - `GraphValidationTransport`
  - `GraphDictionaryTransport`
  - `GraphWorkflowTransport`
  - `GraphRawMutationTransport`
- Normal application code now receives `GraphTransportBundle`, which exposes
  only the first four typed clients. Direct `/entities`, `/claims`, and
  `/relations` writes are no longer available on the default integration
  surface.
- Direct graph mutation methods now live only on
  `GraphRawMutationTransport` with intent-clear names:
  - `upsert_entity_direct`
  - `update_entity_direct`
  - `create_entities_batch_direct`
  - `create_unresolved_claim_direct`
  - `materialize_relation_direct`
- Validation transport methods now reflect their actual meaning:
  - `validate_entity_create`
  - `validate_claim_create`
  - `validate_relation_materialization`
- `GraphAIPreflightService` now depends on narrow typed transport ports plus an
  injected `GraphResolutionCache`, and `document_extraction` no longer keeps a
  module-level singleton preflight service.
- `GraphWorkflowSubmissionService` now owns the only governed bridge from
  normal application code into raw mutation transport.
- Graph-space sync no longer uses blanket admin authority. The DB now reads
  `graph_service_capabilities`, and space sync requires the scoped
  `space_sync` capability.
- Transport-side legacy relation-suggestion rewriting was removed. The DB now
  returns the canonical response shape directly for the constraint-config case.
- Dictionary search/list/proposal transport responses are now typed Pydantic
  models instead of raw JSON-object parsing.
- Repo boundary checks now fail when production code imports
  `GraphRawMutationTransport` outside the explicit allowlist or wraps direct
  `/entities`, `/claims`, or `/relations` writes outside
  `graph_transport.py`.

Final internal shape:

```text
normal app code
  -> GraphTransportBundle
  -> GraphAIPreflightService
  -> GraphWorkflowSubmissionService
  -> artana_evidence_db

raw graph mutation
  -> GraphRawMutationTransport
  -> allowlisted system flows only
```

Acceptance coverage:

- default service tokens carry no admin and no AI principal.
- explicit AI decision submission paths attach `graph_ai_principal`.
- space sync uses `graph_service_capabilities=["space_sync"]` instead of admin.
- raw direct mutation wrappers only exist in `GraphRawMutationTransport`.
- document extraction and relation/entity resolution continue to work through
  the shared typed path.
- boundary validation now fails if a future change reintroduces direct graph
  mutation wrappers outside the allowlisted module.
