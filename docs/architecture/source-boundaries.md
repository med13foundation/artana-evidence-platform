# Source Boundaries

This note defines the source-boundary foundation for issue #16. It is a
contract for future refactors, not a public API change.

## Boundary Rule

Source-specific behavior should be owned once and reused by the registry,
direct search, evidence-selection planning, evidence-selection execution,
handoff, extraction, review, and proposal flow.

The first refactor must not change public route shapes, typed response schemas,
or OpenAPI output. Existing routes and Pydantic models stay stable while source
policy is moved behind clearer internal ownership.

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

## Required Source Policy Fields

Future source-family policy helpers should expose these fields for every
source. A simple source and a variant-aware source should both satisfy the same
contract.

| Field | Meaning |
| --- | --- |
| `source_key` | Stable internal key used by registry, direct search, handoff, and artifacts, such as `pubmed` or `clinvar`. |
| `source_family` | Governed family used for grouping and source-document metadata. Start with existing families such as `literature`, `variant`, `clinical`, `protein`, `structure`, `drug`, and `model_organism`; add new families deliberately with registry and handoff tests. |
| Direct-search capability | `direct_search_supported` plus stable `request_schema_name` and `result_schema_name` when direct search is supported. Unsupported sources leave schema names unset. |
| Provider/external-id keys | Preference-ordered provider record keys used for selection, idempotency, external-ID lookup, and source-document provenance. Reordering can change behavior and should be protected by the future source-boundary contract test. |
| Normalized record shape | The minimal durable record fields handoff can rely on: title/label, source URL when available, summary text, provider metadata, PHI/redaction classification, audit-safe raw record payload, and provider identifier. |
| Variant-aware recommendation behavior | A documented source-owned rule equivalent to `recommends_variant_aware(record) -> bool`. Non-variant sources return `False`; variant-aware sources document the normalized fields the rule reads. This is a documentation-level contract until code policy helpers are introduced. |
| Handoff target policy | Current durable source-search handoff supports `source_document`. Any new target kind requires a code contract update, route/schema review, OpenAPI check, and focused tests before use. |
| Extraction/review/proposal policy | Advisory per-source policy for how captured records should move into extraction, review queues, proposals, or research-plan review before any graph promotion. Central workflow services enforce the final decision. |

## Incremental Order

1. Land docs/contract first: this file names the shared source-policy fields
   and public contract guardrails.
2. Add a tiny dispatcher only if code movement starts to duplicate branching
   across registry, direct search, evidence-selection execution, and handoff.
   If needed, keep it to a `source_key` to policy lookup that exposes the
   required fields above.
3. Move one simple source behind the policy shape, such as
   `clinical_trials`, without changing route contracts.
4. Move one variant-aware source behind the same policy shape, such as
   `clinvar` or `marrvel`, proving variant-aware recommendation behavior fits
   the common contract.
5. Extract an optional direct-search helper only if repeated execution code is
   the blocking duplication. Keep typed request/response models unchanged.
6. Run focused tests and service gates for the touched service before closing
   implementation work.

## Close Criteria For #16

#16 is complete when source ownership is explicit, future policy helpers have
the required fields above, one simple source and one variant-aware source can be
verified against the same boundary contract, and the Evidence API public
contracts remain unchanged. Verification should live in the relevant
`services/artana_evidence_api/tests` tree for service behavior, with
repository-level tests only for cross-service or control-file checks.

Focused regression coverage should include existing handoff replay/idempotency
tests such as `test_source_search_handoff_replays_same_request_and_rejects_conflict`,
`test_sqlalchemy_handoff_store_replays_duplicate_unique_save`, and the
record-hash selection tests in
`services/artana_evidence_api/tests/unit/test_source_search_handoff.py`.
