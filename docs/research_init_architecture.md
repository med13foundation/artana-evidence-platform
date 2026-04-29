# Research Plan Architecture

Status date: April 29, 2026.

Research plan is the Evidence API workflow for starting a new research space
from an objective, seed terms, and selected sources.

Compatibility note: the older research-init route is still available for
existing clients, but current public docs and examples use the v2
`research-plan` entry point.

Public entry point:

- `POST /v2/spaces/{space_id}/research-plan`

Related workflow endpoint:

- `POST /v2/spaces/{space_id}/workflows/topic-setup/tasks`

Related source capability endpoints:

- `GET /v2/sources`
- `GET /v2/sources/{source_key}`
- `POST /v2/spaces/{space_id}/sources/{source_key}/searches`

## Current Flow

```text
research-plan request
  -> build source plan
  -> run PubMed discovery when enabled
  -> run structured-source enrichment when enabled
  -> store source/document records
  -> extract or stage reviewable findings
  -> optionally call research-bootstrap
  -> save task state, outputs, and research state
```

The runtime is queue-aware through the Evidence API task infrastructure. Callers
can inspect task progress, events, outputs, decisions, and working state through
`/v2/spaces/{space_id}/tasks/*`.

## Source Coverage In This Service

Research-plan source keys are registered in
`services/artana_evidence_api/source_registry.py`, while direct-search route
behavior is registered through `services/artana_evidence_api/source_plugins/`.
Together they tell clients which sources support direct search, which sources
run through `research-plan`, and which sources require live external calls or
credentials.

Research-plan runtime currently has service-local source support for:

- PubMed;
- MARRVEL;
- ClinVar;
- MONDO;
- uploaded text;
- uploaded PDF;
- DrugBank;
- AlphaFold;
- UniProt;
- HGNC;
- ClinicalTrials.gov;
- MGI;
- ZFIN.

Direct source search is enabled for bounded source adapters with stable request
and response contracts:

- PubMed;
- MARRVEL;
- ClinVar;
- DrugBank, when `DRUGBANK_API_KEY` is configured;
- AlphaFold;
- UniProt;
- ClinicalTrials.gov;
- MGI;
- ZFIN.

MONDO remains a research-plan/background ontology grounding step rather than a
direct search endpoint. Text and PDF remain document-capture sources. HGNC
remains an enrichment/grounding source.

Generic v2 source-search responses and research-plan-created source documents
include `source_capture` metadata with the source key, capture stage, locator,
query, run/search id, result count, source family, and compact provenance.
Structured direct source searches persist their captured search response in the
Evidence API database so lookup by search id survives process restarts.
Downstream extraction, review items, or proposal staging happen through three
review-gated paths:

- document/extraction workflows for uploaded text and PDFs;
- `research-plan` orchestration for multi-source topic setup;
- direct source-search handoff for one selected captured search record.

The handoff endpoint is
`POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs`.
ClinVar and MARRVEL variant records enter the variant-aware extraction branch.
PubMed, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI, and ZFIN create
durable source documents that preserve the selected record, source-capture
metadata, normalized fields, and audit payload. Handoff output can stage
documents, candidates, proposals, or review items, but it does not directly
promote trusted graph facts.

Live calls to external sources remain environment-dependent. Tests that require
real external APIs are opt-in. PubMed replay bundles are internal test fixtures,
not public source endpoints.

## Bootstrap Relationship

`research_bootstrap_runtime` is a graph-driven child workflow. It can also be
called directly for testing or manual reruns.

```text
research_init_runtime
  -> research_bootstrap_runtime
       -> graph connection
       -> hypothesis generation
       -> claim curation staging
```

The distinction is practical:

- research-plan is document/source heavy;
- bootstrap is graph/reasoning heavy.

## Governance

Research init should stage proposals or review items rather than silently
turning AI output into trusted graph truth. Review happens through:

- `GET /v2/spaces/{space_id}/review-items`
- `POST /v2/spaces/{space_id}/review-items/{item_id}/decision`

Advanced direct-write endpoints still exist, such as
`POST /v2/spaces/{space_id}/sources/marrvel/ingestion`, but normal researcher
workflows should prefer discovery, extraction, and review. Direct source
search and research-plan orchestration both stage work before graph promotion.

## Current Files

| File | Purpose |
| --- | --- |
| `services/artana_evidence_api/routers/research_init.py` | API route |
| `services/artana_evidence_api/source_registry.py` | source capability registry |
| `services/artana_evidence_api/source_plugins/` | source plugin contracts and route registration |
| `services/artana_evidence_api/source_result_capture.py` | normalized source-result capture metadata |
| `services/artana_evidence_api/routers/v2_public.py` | v2 source and research-plan routes |
| `services/artana_evidence_api/research_init_runtime.py` | main runtime |
| `services/artana_evidence_api/research_bootstrap_runtime.py` | graph-driven child runtime |
| `services/artana_evidence_api/research_init_source_enrichment.py` | structured-source orchestration |
| `services/artana_evidence_api/research_init_source_results.py` | shared source-result construction |
| `services/artana_evidence_api/source_document_bridges.py` | source-document and observation bridge |

## Known Architecture Debt

The runtime is still too large and still imports some helper code from router
modules. See [Pending Boundary Issues](./architecture/pending-boundary-issues.md).
