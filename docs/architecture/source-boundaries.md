# Source Boundaries

This note records the source-boundary foundation implemented for issue #16. It
is an internal ownership contract, not a public API change.

## Boundary Rule

Source-specific behavior is owned once and reused by the registry,
direct search, evidence-selection planning, evidence-selection execution,
handoff, extraction, review, and proposal flow.

The source plugin refactor did not change public route shapes, typed response
schemas, or OpenAPI output. Existing routes and Pydantic models stay stable
while source policy lives behind clearer internal ownership.

Per-source policy is advisory metadata and normalization behavior. Central
workflow services remain authoritative for safety, idempotency, review gates,
audit logging, and graph-promotion rules.

## Ownership Model

| Area | Owns | Must Not Own |
| --- | --- | --- |
| Source registry | Public source metadata, source families, capability flags, request/result schema names, and product-facing capture/proposal descriptions. | Live external calls, record normalization, handoff side effects, or review decisions. |
| Direct source search | Typed query execution, external gateway calls, provider response capture, durable `source_search_runs` storage, source-search result metadata, and source-owned timeout/retry/rate-limit defaults. | Goal-to-query planning, relevance selection, extraction policy, or graph promotion. |
| Evidence-selection source planning | Converts user goal and instructions into bounded source intents, validates source allowlists, budgets, limits, and caller-provided timeout overrides. | External source execution details, source-document creation, or trusted graph writes. |
| Evidence-selection source execution | Executes planned source intents through direct-search services and returns durable candidate records for screening. | Reimplementing provider clients or bypassing direct-search persistence. |
| Source handoff | Selects a captured record, normalizes it into a durable source-document/handoff payload, applies idempotency within a research space and source search, and records handoff status. | Public route/schema changes, external provider calls, or reviewer approval. |
| Extraction, review, and proposal policy | Consumes per-source advisory policy and centrally decides whether a handoff becomes extraction input, review item, proposal staging, or research-plan review. | Automatic trusted graph promotion or source-search execution. |

## Current Source Policy Fields

Source plugins expose these fields for every source through
`services/artana_evidence_api/source_plugins/contracts.py` and the explicit
registry in `services/artana_evidence_api/source_plugins/registry.py`. A simple
source, a variant-aware source, an authority source, and a document-ingestion
source all satisfy the same public source-definition contract while using the
right specialized plugin protocol.

| Field | Meaning |
| --- | --- |
| `source_key` | Stable internal key used by registry, direct search, handoff, and artifacts, such as `pubmed` or `clinvar`. |
| `source_family` | Governed family used for grouping and source-document metadata. Start with existing families such as `literature`, `variant`, `clinical`, `protein`, `structure`, `drug`, and `model_organism`; add new families deliberately with registry and handoff tests. |
| Direct-search capability | `direct_search_supported` plus stable `request_schema_name` and `result_schema_name` when direct search is supported. Unsupported sources leave schema names unset. |
| Provider/external-id keys | Preference-ordered provider record keys used for selection, idempotency, external-ID lookup, and source-document provenance. Reordering can change behavior and should be protected by source-boundary contract tests. |
| Normalized record shape | The minimal durable record fields handoff can rely on: title/label, source URL when available, summary text, provider metadata, PHI/redaction classification, audit-safe raw record payload, and provider identifier. |
| Variant-aware recommendation behavior | A source-owned rule equivalent to `recommends_variant_aware(record) -> bool`. Non-variant sources return `False`; variant-aware sources document and test the normalized fields the rule reads. |
| Handoff target policy | Current durable source-search handoff supports `source_document`. Any new target kind requires a code contract update, route/schema review, OpenAPI check, and focused tests before use. |
| Extraction/review/proposal policy | Advisory per-source policy for how captured records should move into extraction, review queues, proposals, or research-plan review before any graph promotion. Central workflow services enforce the final decision. |

## Implemented State

The current Evidence API source boundary has:

1. Direct-search plugins for PubMed, MARRVEL, ClinVar, DrugBank, AlphaFold,
   UniProt, ClinicalTrials.gov, MGI, and ZFIN.
2. Authority plugins for MONDO and HGNC.
3. Document-ingestion plugins for PDF and text.
4. Plugin-backed compatibility facades for older imports such as
   `source_registry.py`, `source_policies.py`,
   `evidence_selection_source_playbooks.py`, and
   `evidence_selection_extraction_policy.py`.
5. A public route plugin layer for typed direct-source routes and generic
   `/sources/{source_key}/searches` dispatch.
6. Focused plugin, route-plugin, registry, parity, source-boundary, and
   evidence-selection tests.

## Keep True For #16

The source-boundary foundation stays complete when source ownership is explicit,
plugin contracts keep the fields above, simple and variant-aware sources can be
verified against the same boundary contract, and the Evidence API public
contracts remain unchanged. Verification should live in the relevant
`services/artana_evidence_api/tests` tree for service behavior, with
repository-level tests only for cross-service or control-file checks.

Focused regression coverage should include existing handoff replay/idempotency
tests such as `test_source_search_handoff_replays_same_request_and_rejects_conflict`,
`test_sqlalchemy_handoff_store_replays_duplicate_unique_save`, and the
record-hash selection tests in
`services/artana_evidence_api/tests/unit/test_source_search_handoff.py`.
