# Research Init Architecture

Status date: April 23, 2026.

Research init is the Evidence API workflow for starting a new research space
from an objective, seed terms, and selected sources.

Entry point:

- `POST /v1/spaces/{space_id}/research-init`

Related direct workflow endpoint:

- `POST /v1/spaces/{space_id}/agents/research-bootstrap/runs`

## Current Flow

```text
research-init request
  -> build source plan
  -> run PubMed discovery when enabled
  -> run structured-source enrichment when enabled
  -> store source/document records
  -> extract or stage reviewable findings
  -> optionally call research-bootstrap
  -> save run state, artifacts, and research state
```

The runtime is queue-aware through the Evidence API run infrastructure. Callers
can inspect run progress, events, artifacts, policy decisions, and workspace
state through `/v1/spaces/{space_id}/runs/*`.

## Source Coverage In This Service

Research-init code currently has service-local source support for:

- PubMed;
- MARRVEL;
- ClinVar;
- DrugBank;
- AlphaFold;
- UniProt;
- ClinicalTrials.gov;
- MGI;
- ZFIN;
- MONDO.

Live calls to external sources remain environment-dependent. Tests that require
real external APIs are opt-in.

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

- research-init is document/source heavy;
- bootstrap is graph/reasoning heavy.

## Governance

Research init should stage proposals or review items rather than silently
turning AI output into trusted graph truth. Review happens through:

- `GET /v1/spaces/{space_id}/review-queue`
- `POST /v1/spaces/{space_id}/review-queue/{item_id}/actions`

Advanced direct-write endpoints still exist, such as
`POST /v1/spaces/{space_id}/marrvel/ingest`, but normal researcher workflows
should prefer discovery, extraction, and review.

## Current Files

| File | Purpose |
| --- | --- |
| `services/artana_evidence_api/routers/research_init.py` | API route |
| `services/artana_evidence_api/research_init_runtime.py` | main runtime |
| `services/artana_evidence_api/research_bootstrap_runtime.py` | graph-driven child runtime |
| `services/artana_evidence_api/research_init_source_enrichment.py` | structured-source orchestration |
| `services/artana_evidence_api/research_init_source_results.py` | shared source-result construction |
| `services/artana_evidence_api/source_document_bridges.py` | source-document and observation bridge |

## Known Architecture Debt

The runtime is still too large and still imports some helper code from router
modules. See [Pending Boundary Issues](./architecture/pending-boundary-issues.md).
