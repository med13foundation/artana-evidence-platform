# Pending Boundary Issues

Status date: April 30, 2026.

The repo is now an extracted two-service backend, but a few architecture issues
remain too large for a narrow patch.

## Evidence API Identity Ownership

Status: partially addressed.

The Evidence API now routes identity and tenancy through
`IdentityGateway`, which gives the codebase a real boundary. The current gateway
is still backed by local Evidence API SQL tables.

Current state:

- low-friction tester access uses `X-Artana-Key`;
- admin tester creation lives at `POST /v2/auth/testers`;
- owner/member checks use the gateway;
- direct identity ORM imports are blocked outside the allowlist by
  `scripts/validate_artana_evidence_api_service_boundary.py`.

Open decision:

- keep identity local while testing remains small, or
- replace `LocalIdentityGateway` with a future remote identity service when
  external-user onboarding, account recovery, audit, or SSO requirements grow.

## Runtime To Router Imports

Status: partially addressed.

The full AI orchestrator no longer imports the private
`research_init_runtime._build_source_results` helper. Shared source-result
construction lives in:

- `services/artana_evidence_api/research_init_source_results.py`

Remaining cleanup:

- move PubMed query/candidate/relevance helpers below router code;
- move PDF enrichment helpers below `routers/documents.py`;
- then add a validator rule that prevents production runtime imports from
  `artana_evidence_api.routers.*`.

## Large Runtime And Workflow Modules

Status: partially addressed; full-AI decomposition slice landed.

The full-AI orchestrator implementation now lives under
`services/artana_evidence_api/full_ai_orchestrator/`. The old root
`full_ai_orchestrator_*.py` files are compatibility facades and should not be
treated as the primary implementation.

The largest remaining modules that still mix several responsibilities are:

- `services/artana_evidence_api/research_init_runtime.py`
- `services/artana_evidence_db/graph_workflow_service.py`

Completed slices:

- research-plan document source classification and selected-source workset
  selection now live in
  `services/artana_evidence_api/research_init_document_selection.py`.
- full-AI execution, queueing, response assembly, progress, guarded decisions,
  shadow summaries, and shadow planner logic now live in focused
  `full_ai_orchestrator/` package modules.

Target split:

- research-plan: source discovery, replay, document preparation, extraction
  staging, state finalization;
- graph workflows: command-family modules once current service gates stay
  stable.

## Deployable Artifact Boundary

Status: guarded by checks, still worth watching.

The intended boundary is HTTP-first: the Evidence API should consume graph
contracts and graph HTTP endpoints, not graph internals. Keep this protected
with:

- `make artana-evidence-api-boundary-check`
- `make graph-service-boundary-check`
- `make graph-service-contract-check`
- `make artana-evidence-api-contract-check`
