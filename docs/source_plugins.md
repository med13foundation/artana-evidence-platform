# Source Plugin Developer Guide

This guide explains how evidence sources are represented in the Evidence API.

The key rule is:

> Everything can be an evidence source, but not everything is a live searchable
> datasource.

## Source Types

### Direct-Search Sources

Use a direct-search plugin when the platform can query an external source and
persist returned records as direct source-search results.

Examples:

- PubMed
- MARRVEL
- ClinVar
- DrugBank
- AlphaFold
- gnomAD
- UniProt
- ClinicalTrials.gov
- MGI
- ZFIN

Direct-search plugins implement the `EvidenceSourcePlugin` contract through:

- source metadata;
- query planning;
- live-search validation;
- live-search execution or execution delegation;
- record normalization;
- provider external ID extraction;
- variant-aware recommendation;
- extraction/review policy;
- candidate context construction.

Direct-search plugins are explicitly registered in
`services/artana_evidence_api/source_plugins/registry.py`.

### Authority Sources

Use an authority plugin when the source grounds entities to normalized IDs,
labels, aliases, and provenance.

Examples:

- MONDO for disease grounding.
- HGNC for gene-symbol grounding.

Authority plugins implement `AuthoritySourcePlugin`. They return
`SourceGroundingContext` with one of three statuses:

- `resolved`
- `ambiguous`
- `not_found`

Authority plugins must not auto-promote claims. Their job is to make extracted
evidence safer and better normalized.

### Document-Ingestion Sources

Use a document-ingestion plugin when the user provides the evidence content.

Examples:

- PDF uploads.
- Text evidence.

Document-ingestion plugins implement `DocumentIngestionSourcePlugin`. They:

- validate input source kind and content type;
- normalize document metadata;
- return `SourceDocumentIngestionContext`.

They must not persist documents, call extractors, enqueue review items, or
promote evidence. Orchestration owns those side effects.

## Adding A Direct-Search Source

1. Add or update the public `SourceDefinition` in `source_registry.py`.
2. Add a focused plugin module under `source_plugins/`.
3. Register the plugin in `_SOURCE_PLUGINS` in `source_plugins/registry.py`.
4. Add source-specific plugin tests.
5. Add generic parity fixtures while compatibility maps still exist.
6. Confirm the source does not appear in legacy live-search maps.

Run:

```bash
venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py -q
make artana-evidence-api-type-check
make artana-evidence-api-contract-check
```

## Adding An Authority Source

1. Add or update the public `SourceDefinition`.
2. Add a focused authority plugin module under `source_plugins/authority/`.
3. Register it in `_AUTHORITY_SOURCE_PLUGINS`.
4. Test resolved, ambiguous, and not-found grounding.
5. Ensure it is not included in `direct_search_source_keys()`.

Run:

```bash
venv/bin/pytest services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py -q
make artana-evidence-api-type-check
```

## Adding A Document-Ingestion Source

1. Add or update the public `SourceDefinition`.
2. Add a focused ingestion plugin module under `source_plugins/ingestion/`.
3. Register it in `_DOCUMENT_INGESTION_SOURCE_PLUGINS`.
4. Test valid metadata normalization and rejected invalid content types.
5. Ensure persistence, extraction, review, and promotion stay outside the
   plugin.

Run:

```bash
venv/bin/pytest services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py -q
make artana-evidence-api-type-check
```

## Compatibility Facades

The following central files still exist as compatibility and parity surfaces:

- `source_registry.py`
- `source_policies.py`
- `evidence_selection_source_playbooks.py`
- `evidence_selection_extraction_policy.py`
- `direct_source_search.py`

New source-specific behavior should go into source plugins first. Central maps
should only remain when they are part of public compatibility, route schemas, or
temporary parity tests.

### Public Route Compatibility Branches

The public API still exposes concrete typed routes per direct-search source
because each source has its own request and response schemas. Those concrete
route declarations do not live in `routers/v2_public.py`; they live behind
route plugins.

`source_route_plugins.py` registers typed direct-source route plugins in the
same order as `direct_search_source_keys()`. Focused `source_route_*.py`
modules own route paths, request/response model binding, route dependencies,
OpenAPI summaries, generic-route payload parsing, gateway execution, and
compatibility response shaping for each source.

`routers/v2_public.py` only calls `register_direct_source_typed_routes(router)`
before registering the generic source-search routes. The generic source-search
routes delegate through `source_route_plugins.py` instead of branching on
source keys:

- `create_source_search`
- `get_source_search`

The route plugin layer owns public API compatibility parsing, response shaping,
typed route registration, and generic source-key dispatch. It is split into the
route plugin registry (`source_route_plugins.py`), generic dependency assembly
(`source_route_dependencies.py`), shared route helpers/errors, shared route
contracts, and focused source-specific route modules. Keep each module under
the architecture-size budget and split new source-specific route behavior
before it turns into another central router. Generic route functions must
remain source-agnostic; tests guard that they do not reintroduce source-key
branches. New source behavior should still land in the source plugin first;
route code may call stable compatibility helpers only to preserve public API
shape.

Existing path-parameter names are intentionally preserved for compatibility:
PubMed uses `{job_id}`, MARRVEL uses `{result_id}`, and the other direct-search
sources use `{search_id}`. New source routes should prefer `{search_id}` unless
they are preserving an existing public contract.

MARRVEL has one intentional default split:

- planner-generated plugin searches default to the focused panel set
  `omim`, `clinvar`, `gnomad`, `geno2mp`, and `expression`;
- direct user/API searches with no `panels` value keep the existing discovery
  behavior and request all supported MARRVEL panels.

This keeps harness planning bounded without narrowing the public exploratory
MARRVEL API.

## Guardrails

Do not:

- add one large `source_plugins.py` file;
- add flat non-direct modules like `source_plugins/mondo.py` or
  `source_plugins/pdf.py`;
- register plugins through import side effects;
- put database sessions, routers, SQLAlchemy models, graph-service internals,
  or review-item persistence inside plugins;
- make document-ingestion plugins dispatch extraction/review side effects;
- add new source-key live-search handler maps outside the plugin registry.
