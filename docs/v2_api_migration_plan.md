# V2 API Migration Plan

Status date: April 24, 2026.

This plan covers the work required to move the Evidence API from a
runtime-shaped v1 surface to a product-shaped v2 surface. Source-registry and
direct source-search work is tracked in `docs/plan.md`.

Current status:

- v2 route aliases exist and are mounted.
- v2 route coverage is tested at the router and OpenAPI level.
- v2 source capability endpoints exist for public source discovery.
- PubMed and MARRVEL direct search flow through the generic v2 source-search
  route shape.
- ClinVar, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI, and ZFIN
  also flow through the generic v2 source-search route shape when their
  gateways are available. DrugBank requires `DRUGBANK_API_KEY`.
- Typed v2 source-search routes remain available for generated-client schemas
  and for PubMed, MARRVEL, ClinVar, ClinicalTrials.gov, UniProt, AlphaFold,
  DrugBank, MGI, and ZFIN.
- Generic source-search responses carry normalized `source_capture` provenance
  metadata.
- Structured direct source-search responses are persisted as durable Evidence
  API source-search runs; direct search does not promote graph facts.
- v1 remains the dominant surface in docs, scripts, tests, and payload names.

Target outcome:

```text
v2
  -> primary public API surface
  -> primary docs and examples
  -> primary smoke and user-flow tests
  -> stable request/response naming

v1
  -> compatibility layer only
  -> explicitly deprecated
  -> removable after cutover window
```

## Naming Direction

The public contract should use these v2 terms consistently:

| v1 | v2 |
| --- | --- |
| `runs` | `tasks` |
| `agents/*/runs` | `workflows/*/tasks` |
| `review-queue` | `review-items` |
| `graph-explorer` | `evidence-map` |
| `graph-write-candidates` | `suggested-updates` |
| `artifacts` | `outputs` |
| `policy-decisions` | `decisions` |
| `research-init` | `research-plan` |
| `research-bootstrap` | `topic-setup` |
| `graph-curation` | `evidence-curation` |
| `full-ai-orchestrator` | `autopilot` |
| `harnesses` | `workflow-templates` |

Source-specific endpoints should use the generic source shape when possible:

| Older shape | v2 direction |
| --- | --- |
| `pubmed/searches` | `sources/{source_key}/searches` |
| `marrvel/searches` | `sources/{source_key}/searches` |
| source flags hidden in settings | `GET /v2/sources` capability discovery |

## Workstreams

### 1. Freeze The V2 Path Contract

Goal:
Keep the v2 route map stable while the rest of the cutover work lands.

Tasks:

- Keep `services/artana_evidence_api/routers/v2_public.py` as the source of
  truth for public path naming.
- Add a short mapping table from v1 to v2 in the service docs and user guide.
- Decide which v1 endpoints are intentionally v1-only and document them.

Exit criteria:

- Every intended public v1 endpoint has a v2 counterpart.
- The route map is documented in one place and tested.

### 2. Rename Public Request And Response Shapes

Goal:
Stop leaking runtime nouns like `run`, `run_id`, and `harness_id` in v2
payloads.

Tasks:

- Introduce v2 request and response models where the public names differ:
  - `task_id` instead of `run_id`
  - `workflow_template_id` instead of `harness_id`
  - `outputs` instead of `artifacts`
  - `decisions` instead of `policy_decisions`
- Update any returned links such as `poll_url`, `stream_url`, or workspace
  references so they point at v2 paths.
- Add regression tests that compare v1 and v2 behavior while allowing the
  public field names to differ.

Exit criteria:

- v2 path names and v2 payload names tell the same story.
- No v2 response body needs v1 knowledge to understand it.

### 3. Move Product Docs To V2

Goal:
Make v2 the default path readers see first.

Priority docs:

- `docs/user-guide/02-core-concepts.md`
- `docs/user-guide/03-workflow-overview.md`
- `docs/user-guide/04-adding-evidence.md`
- `docs/user-guide/05-reviewing-and-promoting.md`
- `docs/user-guide/06-exploring-and-asking.md`
- `docs/user-guide/07-multi-source-and-automation.md`
- `docs/user-guide/08-runtime-debugging-and-transparency.md`
- `services/artana_evidence_api/docs/getting-started.md`
- `services/artana_evidence_api/docs/use-cases.md`
- `services/artana_evidence_api/docs/user-guide.md`
- `services/artana_evidence_api/docs/full-research-workflow.md`
- `docs/full_AI_orchestrator.md`
- `docs/research_init_architecture.md`

Tasks:

- Rewrite examples and curl snippets to use v2 first.
- Update product wording so the docs say `tasks`, `workflows`,
  `review-items`, and `evidence-map`.
- Keep a short v1 compatibility note where helpful, but stop centering v1 in
  the main flow.

Exit criteria:

- A new user can learn the platform from docs without seeing v1 first.
- The user guide, getting-started guide, and API reference all agree on v2.

### 4. Move Tests And Smoke Scripts To V2

Goal:
Make v2 the default tested surface, not just an alias layer.

Priority test and script areas:

- `services/artana_evidence_api/tests/e2e/`
- `services/artana_evidence_api/tests/integration/test_runtime_paths.py`
- `services/artana_evidence_api/tests/unit/test_app.py`
- `tests/e2e/artana_evidence_api/`
- `scripts/run_live_evidence_smoke_suite.py`
- `scripts/run_live_evidence_session_audit.py`
- `scripts/run_full_ai_real_space_canary.py`
- `scripts/run_full_ai_settings_canary_cycle.py`
- `scripts/issue_artana_evidence_api_key.py`

Tasks:

- Add v2-first test helpers so future tests do not reintroduce v1 by default.
- Move smoke, contract, and user-flow tests to call v2 routes.
- Keep a focused v1 compatibility test set instead of duplicating every flow
  forever.

Exit criteria:

- The main Evidence API smoke and user-flow tests exercise v2.
- v1 has targeted compatibility coverage instead of being the default path in
  broad suites.

### 5. Update SDK And Client Generation Story

Goal:
Make generated clients and future SDK consumers see clean v2 names.

Tasks:

- Review generated OpenAPI operation ids for stable v2 naming.
- Decide whether the next public client should be generated directly from v2
  OpenAPI or wrapped by a small handwritten layer.
- Ensure schema names, examples, and tags are consistent enough for client
  generation.

Exit criteria:

- A generated or handwritten client can expose v2 nouns without awkward v1
  type names leaking through.

### 6. Add V1 Deprecation And Removal Policy

Goal:
Prevent v1 and v2 from drifting indefinitely.

Tasks:

- Decide when v1 becomes deprecated in OpenAPI and docs.
- Add a short deprecation note to v1-focused docs once v2 is primary.
- Keep a removal checklist for the eventual v1 deletion pass:
  - remove v1 docs examples
  - remove v1 smoke paths
  - remove v1 router surface
  - regenerate contracts
  - rerun service checks

Exit criteria:

- The repo has an explicit answer to "how long do we keep v1?"

## Suggested Sequence

1. Finish v2 payload/schema renames.
2. Move top-level docs and user-guide examples to v2.
3. Move smoke scripts and broad user-flow tests to v2.
4. Reduce v1 test coverage to compatibility checks.
5. Mark v1 deprecated.
6. Remove v1 after the agreed cutover window.

## Definition Of Done

The repo has completed the v2 cutover when all of the following are true:

- v2 is the default path in docs, examples, smoke tests, and user flows.
- v2 payloads no longer leak core v1 nouns that matter to end users.
- OpenAPI and client-generation outputs present v2 as the primary contract.
- v1 is compatibility-only and explicitly deprecated.
- `make artana-evidence-api-service-checks` remains green throughout.

## Immediate Next Tasks

- [ ] Inventory v2 payload fields that still leak `run` or `harness` nouns.
- [ ] Update the highest-traffic docs from v1 to v2.
- [ ] Convert live smoke and user-flow scripts to v2.
- [ ] Add a narrow v1 compatibility suite so we can stop using v1 everywhere.
- [ ] Decide the v1 deprecation window.
